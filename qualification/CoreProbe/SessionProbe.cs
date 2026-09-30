using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Text.Json;
using Flight.Core;
using Flight.Data;
using Flight.Presentation;

internal static class SessionProbe
{
    private const int Steps = 1024;
    private static void Require(bool condition, string message) { if (!condition) throw new Exception(message); }
    private static byte[] Bytes(SimulationSession session) => SessionCodec.Encode(session.Capture());
    private static void Command(SimulationSession session, int tick)
    {
        FlightAssistMode? mode = tick switch
        {
            128 or 384 => FlightAssistMode.AttitudeHold, 192 => FlightAssistMode.KillRotation,
            256 or 768 => FlightAssistMode.Manual, 600 => FlightAssistMode.ProgradeHold, _ => null
        };
        if (mode is {} selected) session.SelectAssist(selected);
        FlightInput input = tick < 128 || tick is >=256 and <320 ? new(333,23,-17,7,8,-9,11) :
            tick is >=400 and <448 ? new(217,1,2,3,0,0,0) : default;
        session.Step(input);
    }

    internal static void Run(string data, string output)
    {
        Require(!Directory.Exists(output), "fresh session output required"); Directory.CreateDirectory(output);
        SimulationSession a=Fixtures.Lunar(data), b=Fixtures.Lunar(data);
        using FileStream file=File.Create(Path.Combine(output,"expected.jsonl.gz"));
        using GZipStream gzip=new(file,CompressionLevel.Fastest);
        int restored=0;
        for (int tick=0;tick<=Steps;tick++)
        {
            Require(!a.IsStopped && !b.IsStopped && a.Tick==tick && b.Tick==tick,"unexpected session stop: "+a.Diagnostic);
            byte[] left=Bytes(a),right=Bytes(b);
            Require(left.AsSpan().SequenceEqual(right),"complete session mismatch at "+tick);
            gzip.Write(left);gzip.WriteByte(10);
            if(tick==Steps/2)
            {
                File.WriteAllBytes(Path.Combine(output,"midpoint.json"),right);
                b=Fixtures.Lunar(data);b.Restore(SessionCodec.Decode(File.ReadAllBytes(Path.Combine(output,"midpoint.json"))));
                Require(right.AsSpan().SequenceEqual(Bytes(b)),"hidden session state lost at restore");restored++;
            }
            if(tick==Steps) {File.WriteAllBytes(Path.Combine(output,"endpoint.json"),left);break;}
            Command(a,tick);Command(b,tick);
        }
        FlightSessionSnapshot accepted=b.Capture();byte[] before=Bytes(b);
        FlightSessionSnapshot bad=accepted with { DynamicsVersion="qualification-wrong-version" };
        bool versionRejected=false;try {b.Restore(bad);}catch(InvalidDataException){versionRejected=true;}
        Require(versionRejected && before.AsSpan().SequenceEqual(Bytes(b)),"version rejection mutated state");
        bool malformedRejected=false;try {SessionCodec.Decode(before[..^1]);}catch(Exception e) when(e is JsonException or InvalidDataException){malformedRejected=true;}
        Require(malformedRejected && before.AsSpan().SequenceEqual(Bytes(b)),"malformed rejection mutated state");
        var mutation=accepted with {Physical=accepted.Physical with {Vessel=accepted.Physical.Vessel with {PropellantMicrograms=accepted.Physical.Vessel.PropellantMicrograms-1}}};
        Require(!before.AsSpan().SequenceEqual(SessionCodec.Encode(mutation)),"one-microgram mutation escaped comparison");
        Inventory(typeof(KinematicState),"PositionMm,PositionRemainder,VelocityNmPerSec,VelocityRemainder");
        Inventory(typeof(VesselState),"AngularVelocityNradPerSec,AngularVelocityRemainder,Attitude,LastMainThrustMilliNewtons,LastMainThrustNanoNewtons,LastRcsForceMilliNewtons,LastThrustAccelerationFmPerS2,LastTorqueMilliNewtonMetres,MainFuelRemainder,PositionMm,PositionRemainder,PropellantMicrograms,RcsFuelRemainder,VelocityNmPerSec,VelocityRemainder");
        Inventory(typeof(FlightState),"Bodies,ContentIdentity,Diagnostic,IsStopped,Tick,Vessel");
        Report(output,"session-replay.json",new{compared_complete_states=Steps+1,midpoint_restore=restored,version_rejection_preserved_state=true,
            malformed_rejection_preserved_state=true,one_microgram_mutation_detected=true,mutable_physical_inventory_matched=true,
            scope="full physical and guidance snapshots, commands and last accepted command; mission is absent in this fixture; same runtime only"});
    }

    internal static void Interrupt(string data,string output)
    {
        string path=Path.Combine(output,"interrupted-midpoint.json");Require(!File.Exists(path),"interruption evidence already exists");
        var session=Fixtures.Lunar(data);for(int tick=0;tick<Steps/2;tick++)Command(session,tick);
        using(var file=new FileStream(path,FileMode.CreateNew,FileAccess.Write,FileShare.None)){file.Write(Bytes(session));file.Flush(true);}
        Environment.Exit(23);
    }

    internal static void Resume(string data,string output)
    {
        Require(!File.Exists(Path.Combine(output,"fresh-process-resume.json")),"resume evidence already exists");
        var session=Fixtures.Lunar(data);session.Restore(SessionCodec.Decode(File.ReadAllBytes(Path.Combine(output,"interrupted-midpoint.json"))));
        using var file=File.OpenRead(Path.Combine(output,"expected.jsonl.gz"));
        using var gzip=new GZipStream(file,CompressionMode.Decompress);using var reader=new StreamReader(gzip,new UTF8Encoding(false,true));
        int comparisons=0;
        for(int tick=0;tick<=Steps;tick++)
        {
            string line=reader.ReadLine()??throw new Exception("truncated baseline");if(tick<Steps/2)continue;
            Require(session.Tick==tick && !session.IsStopped,"resumed branch stopped");
            Require(Encoding.UTF8.GetBytes(line).AsSpan().SequenceEqual(Bytes(session)),"fresh-process complete bytes differ at "+tick);
            comparisons++;if(tick<Steps)Command(session,tick);
        }
        Require(reader.ReadLine() is null,"extra baseline states");
        Require(File.ReadAllBytes(Path.Combine(output,"endpoint.json")).AsSpan().SequenceEqual(Bytes(session)),"resumed endpoint differs");
        Report(output,"fresh-process-resume.json",new{compared_complete_states=comparisons,start_tick=Steps/2,end_tick=Steps,complete_bytes_equal=true,
            scope="new process after deliberate exit23 following durable snapshot write; no incomplete-write or automatic recovery claim"});
    }

    private static void Inventory(Type type,string expected)
    {
        string actual=string.Join(",",type.GetProperties(BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic).Where(p=>p.SetMethod is not null).Select(p=>p.Name).Order(StringComparer.Ordinal));
        Require(actual==expected,"mutable authority inventory changed: "+type.Name);
    }
    private static void Report(string root,string name,object value)
    {string json=JsonSerializer.Serialize(value,new JsonSerializerOptions{WriteIndented=true});File.WriteAllText(Path.Combine(root,name),json);Console.WriteLine(json);}
}
