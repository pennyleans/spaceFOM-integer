using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using Flight.Core;
using Flight.Data;

if (args.Length < 3) throw new ArgumentException("case <name> <rate> <data> <fresh-output> | session <data> <fresh-output> | resume <data> <existing-session-output>");
if (args[0] == "session") { SessionProbe.Run(args[1], args[2]); return; }
if (args[0] == "resume") { SessionProbe.Resume(args[1], args[2]); return; }
if (args[0] == "interrupt") { SessionProbe.Interrupt(args[1], args[2]); return; }
if (args[0] != "case" || args.Length != 5) throw new ArgumentException("invalid command");
string name = args[1], data = args[3], output = args[4];
int rate = int.Parse(args[2], System.Globalization.CultureInfo.InvariantCulture);
if (Directory.Exists(output)) throw new IOException("fresh output directory required");
Directory.CreateDirectory(output);
FlightState a = Fixtures.Create(name, rate, data), b = Fixtures.Create(name, rate, data);
File.WriteAllText(Path.Combine(output,"initial.json"), Observations.Initial(name,a));
using StreamWriter samples = new(Path.Combine(output,"samples.jsonl"));
using FileStream trace = File.Create(Path.Combine(output,"canonical-digests.bin"));
long steps = (long)Fixtures.Seconds(name)*rate;
Stopwatch timer = Stopwatch.StartNew();
int restores = 0;
for (long tick = 0; tick <= steps; tick++)
{
    if (a.Tick != tick || b.Tick != tick || a.IsStopped || b.IsStopped) throw new Exception("unexpected stopped or skipped tick: " + a.Diagnostic);
    byte[] left = SessionCodec.Encode(PhysicalSnapshot.Capture(a)), right = SessionCodec.Encode(PhysicalSnapshot.Capture(b));
    if (!left.AsSpan().SequenceEqual(right)) throw new Exception("complete physical bytes differ at tick " + tick);
    trace.Write(SHA256.HashData(left));
    if (tick % rate == 0) samples.WriteLine(Observations.Sample(a));
    if (tick == steps/2)
    {
        File.WriteAllBytes(Path.Combine(output,"midpoint.json"), right);
        b = SessionCodec.Decode<PhysicalSnapshot>(File.ReadAllBytes(Path.Combine(output,"midpoint.json"))).Restore();
        if (!right.AsSpan().SequenceEqual(SessionCodec.Encode(PhysicalSnapshot.Capture(b)))) throw new Exception("midpoint restore changed complete bytes");
        restores++;
    }
    if (tick == steps) { File.WriteAllBytes(Path.Combine(output,"endpoint.json"), left); break; }
    FlightCommand command = Fixtures.Command(name,tick,rate);
    FlightEngine.Step(a,command); FlightEngine.Step(b,command);
    if ((tick+1) % (rate*600L) == 0) Console.WriteLine($"{name}/{rate}: {tick+1}/{steps}");
}
samples.Flush(); trace.Flush();
var receipt = new { schema="qualification-physical-replay-v1", @case=name, rate_hz=rate,
    compared_complete_states=steps+1, compared_bytes_exact=true, midpoint_serialized_restores=restores,
    duration_seconds=Fixtures.Seconds(name), elapsed_wall_seconds=timer.Elapsed.TotalSeconds,
    dynamics=FlightEngine.DynamicsVersion, final_physical_hash=a.ComputeStateHash(),
    scope="same-process independent genesis and complete-byte comparison at every tick; serialized midpoint restore; numerical accuracy assessed separately" };
string json=JsonSerializer.Serialize(receipt,new JsonSerializerOptions{WriteIndented=true});
File.WriteAllText(Path.Combine(output,"replay.json"),json); Console.WriteLine(json);
