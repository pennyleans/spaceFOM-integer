using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using Flight.Core;
using Flight.Data;

if(args.Length<4) throw new ArgumentException("case <name> <power> <data> <output> | bench <power> <ticks> <data> <output> | session <power> <data> <output>");
if(args[0]=="spin") {SpinBenchmark.Run(int.Parse(args[1]),int.Parse(args[2]),args[3],args[4]);return;}
if(args[0]=="bench") {Benchmark.Run(int.Parse(args[1]),int.Parse(args[2]),args[3],args[4]);return;}
if(args[0] is "session" or "interrupt" or "resume")
{
    Fixtures.Power=int.Parse(args[1]);
    if(args[0]=="session") SessionProbe.Run(args[2],args[3]);
    if(args[0]=="interrupt") SessionProbe.Interrupt(args[2],args[3]);
    if(args[0]=="resume") SessionProbe.Resume(args[2],args[3]);
    return;
}
if(args[0]!="case" || args.Length!=5) throw new ArgumentException("invalid command");
string name=args[1],data=args[3],output=args[4];
Fixtures.Power=int.Parse(args[2]);
const int rate=64;
if(Directory.Exists(output)) throw new IOException("fresh output required");
Directory.CreateDirectory(output);
FlightState a=Fixtures.Create(name,rate,data),b=Fixtures.Create(name,rate,data);
File.WriteAllText(Path.Combine(output,"initial.json"),Observations.Initial(name,a));
using StreamWriter samples=new(Path.Combine(output,"samples.jsonl"));
using FileStream trace=File.Create(Path.Combine(output,"canonical-digests.bin"));
long steps=(long)Fixtures.Seconds(name)*rate;
Stopwatch timer=Stopwatch.StartNew();
for(long tick=0;tick<=steps;tick++)
{
    if(a.Tick!=tick || b.Tick!=tick || a.IsStopped || b.IsStopped) throw new Exception("unexpected stop: "+a.Diagnostic);
    byte[] left=SessionCodec.Encode(PhysicalSnapshot.Capture(a)),right=SessionCodec.Encode(PhysicalSnapshot.Capture(b));
    if(!left.AsSpan().SequenceEqual(right)) throw new Exception("complete physical mismatch at "+tick);
    trace.Write(SHA256.HashData(left));
    if(tick%rate==0) samples.WriteLine(Observations.Sample(a));
    if(tick==steps/2)
    {
        File.WriteAllBytes(Path.Combine(output,"midpoint.json"),right);
        b=SessionCodec.Decode<PhysicalSnapshot>(right).Restore();
        if(!right.AsSpan().SequenceEqual(SessionCodec.Encode(PhysicalSnapshot.Capture(b)))) throw new Exception("restore changed bytes");
    }
    if(tick==steps){File.WriteAllBytes(Path.Combine(output,"endpoint.json"),left);break;}
    FlightCommand command=Fixtures.Command(name,tick,rate);
    FlightEngine.Step(a,command);FlightEngine.Step(b,command);
    if((tick+1)%(rate*600L)==0) Console.WriteLine($"{name}/{1<<Fixtures.Power}: {tick+1}/{steps}");
}
samples.Flush();trace.Flush();
var receipt=new{schema="precision-physical-replay-v1",@case=name,rate_hz=rate,integration_substeps=1<<Fixtures.Power,
    compared_complete_states=steps+1,compared_bytes_exact=true,midpoint_serialized_restores=1,duration_seconds=Fixtures.Seconds(name),
    elapsed_wall_seconds=timer.Elapsed.TotalSeconds,dynamics=FlightEngine.DynamicsVersionFor(a),final_physical_hash=a.ComputeStateHash(),
    scope="complete physical comparison every outer tick; full accuracy assessed independently"};
string json=JsonSerializer.Serialize(receipt,new JsonSerializerOptions{WriteIndented=true});
File.WriteAllText(Path.Combine(output,"replay.json"),json);Console.WriteLine(json);
