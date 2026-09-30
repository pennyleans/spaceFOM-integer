using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Flight.Core;
using Flight.Data;
using Flight.Presentation;

// Regenerates the published per-tick state digests and compares them with the recorded hashes.
string root = AppContext.BaseDirectory;
string data = Path.Combine(root, "data");
string expectedPath = Path.Combine(root, "expected.json");
string? receiptPath = null;
bool quick = false;
for (int i = 0; i < args.Length; i++)
{
    switch (args[i])
    {
        case "--quick": quick = true; break;
        case "--data" when i + 1 < args.Length: data = args[++i]; break;
        case "--expected" when i + 1 < args.Length: expectedPath = args[++i]; break;
        case "--receipt" when i + 1 < args.Length: receiptPath = args[++i]; break;
        default:
            Console.Error.WriteLine("usage: 2207-verify [--quick] [--receipt <file>] [--data <dir>] [--expected <file>]");
            return 2;
    }
}

JsonNode expected = JsonNode.Parse(File.ReadAllText(expectedPath)) ?? throw new InvalidDataException("empty expected file");
Fixtures.Power = (int)expected["integration_substep_power"]!;
string[] quickSet = ["inertial-burn", "lunar-fixture"];
List<Check> checks = [];
foreach (JsonNode? node in expected["scenarios"]!.AsArray())
{
    string name = (string)node!["name"]!;
    if (!quick || quickSet.Contains(name)) checks.Add(new(name, (long)node["states"]!, (string)node["digest_stream_sha256"]!));
}
JsonNode session = expected["session"]!;
checks.Add(new("session", (long)session["records"]!, (string)session["record_stream_sha256"]!));

Console.WriteLine("2207: Integer Spaceflight Simulator replay verification");
Console.WriteLine($"platform   {RuntimeInformation.OSDescription.Trim()} ({RuntimeInformation.ProcessArchitecture})");
Console.WriteLine($"runtime    {RuntimeInformation.FrameworkDescription}");
Console.WriteLine($"source     {FlightAuthorityIdentity.Value}");
Console.WriteLine($"expected   {(string)expected["source_identity"]!}");
Console.WriteLine($"scenarios  {(quick ? "quick subset" : "all")}; running in parallel");
Console.WriteLine();

Stopwatch total = Stopwatch.StartNew();
Result[] results = await Task.WhenAll(checks.Select(check => Task.Run(() => check.Name == "session" ? Session(check, data) : Physical(check, data))));

Console.WriteLine($"{"scenario",-26} {"states",9} {"seconds",8}  result");
foreach (Result result in results)
    Console.WriteLine($"{result.Name,-26} {result.States,9:N0} {result.Seconds,8:F1}  {(result.Match ? "match" : "DIFFERS")}");
bool sourceMatches = FlightAuthorityIdentity.Value == (string)expected["source_identity"]!;
bool pass = sourceMatches && results.All(result => result.Match);
long compared = results.Sum(result => result.States);
Console.WriteLine();
Console.WriteLine(pass
    ? $"PASS: all {compared:N0} states match the published hashes ({total.Elapsed.TotalSeconds:F0} s)."
    : sourceMatches ? "FAIL: at least one digest stream differs from the published hash." : "FAIL: this build does not use the published source revision.");

if (receiptPath is not null)
{
    var receipt = new
    {
        schema = "2207-verify-receipt-v1",
        pass,
        quick,
        platform = RuntimeInformation.OSDescription.Trim(),
        architecture = RuntimeInformation.ProcessArchitecture.ToString(),
        runtime = RuntimeInformation.FrameworkDescription,
        source_identity = FlightAuthorityIdentity.Value,
        results = results.Select(result => new { scenario = result.Name, states = result.States, sha256 = result.Observed, expected_sha256 = result.Expected, match = result.Match }),
    };
    File.WriteAllText(receiptPath, JsonSerializer.Serialize(receipt, new JsonSerializerOptions { WriteIndented = true }) + "\n");
}
return pass ? 0 : 1;

// Hashes the concatenated SHA-256 digests of each tick's canonical physical snapshot, as in qualification/precision64/Probe.
static Result Physical(Check check, string data)
{
    Stopwatch timer = Stopwatch.StartNew();
    const int rate = 64;
    FlightState state = Fixtures.Create(check.Name, rate, data);
    long steps = (long)Fixtures.Seconds(check.Name) * rate;
    using IncrementalHash stream = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
    for (long tick = 0; tick <= steps; tick++)
    {
        if (state.Tick != tick || state.IsStopped) throw new InvalidOperationException($"{check.Name} stopped at tick {tick}: {state.Diagnostic}");
        stream.AppendData(SHA256.HashData(SessionCodec.Encode(PhysicalSnapshot.Capture(state))));
        if (tick < steps) FlightEngine.Step(state, Fixtures.Command(check.Name, tick, rate));
    }
    return new(check.Name, steps + 1, timer.Elapsed.TotalSeconds, Convert.ToHexStringLower(stream.GetHashAndReset()), check.Expected);
}

// Hashes each complete session record followed by a newline, as in qualification/precision64/Probe/SessionProbe.cs.
static Result Session(Check check, string data)
{
    Stopwatch timer = Stopwatch.StartNew();
    const int steps = 1024;
    SimulationSession session = Fixtures.Lunar(data);
    using IncrementalHash stream = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
    for (int tick = 0; tick <= steps; tick++)
    {
        if (session.Tick != tick || session.IsStopped) throw new InvalidOperationException($"session stopped at tick {tick}");
        stream.AppendData(SessionCodec.Encode(session.Capture()));
        stream.AppendData("\n"u8);
        if (tick == steps) break;
        FlightAssistMode? mode = tick switch
        {
            128 or 384 => FlightAssistMode.AttitudeHold, 192 => FlightAssistMode.KillRotation,
            256 or 768 => FlightAssistMode.Manual, 600 => FlightAssistMode.ProgradeHold, _ => null
        };
        if (mode is { } selected) session.SelectAssist(selected);
        FlightInput input = tick < 128 || tick is >= 256 and < 320 ? new(333, 23, -17, 7, 8, -9, 11) :
            tick is >= 400 and < 448 ? new(217, 1, 2, 3, 0, 0, 0) : default;
        session.Step(input);
    }
    return new(check.Name, steps + 1, timer.Elapsed.TotalSeconds, Convert.ToHexStringLower(stream.GetHashAndReset()), check.Expected);
}

internal sealed record Check(string Name, long States, string Expected);

internal sealed record Result(string Name, long States, double Seconds, string Observed, string Expected)
{
    public bool Match => Observed == Expected;
}
