using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using Flight.Data;
using Flight.Presentation;
using Flight.Shared;

internal static class Benchmark
{
    internal static void Run(int power,int count,string data,string output)
    {
        if(count<256 || count>32768 || power is <0 or >5)throw new ArgumentException("invalid bounded benchmark");
        if(Directory.Exists(output))throw new IOException("fresh benchmark output required");
        Directory.CreateDirectory(output);
        const int warmup=1024;
        foreach(string workload in new[]{"coast","coupled-controls"})
        {
            SimulationSession initial=new(SolarCatalog.Load(Path.Combine(data,"sol-2207.json")),
                ShipLoader.Load(Path.Combine(data,"ships/reference-tug.ship.toml"),Path.Combine(data,"ships/reference-tug.flight.json")),integrationSubstepPower:power);
            SharedSession shared=new(initial);
            double[] elapsed=new double[count];
            string lastHash="";int lastViewBytes=0;
            long sequence=0;
            for(int i=0;i<warmup+count;i++)
            {
                long frame=shared.Frame+1;
                CommandPatch[] p1=[],p2=[];
                if(workload=="coupled-controls" && i%32==0)
                {
                    int cycle=(i/32)%8;
                    FlightAssistMode assist=cycle switch{2=>FlightAssistMode.KillRotation,4=>FlightAssistMode.AttitudeHold,6=>FlightAssistMode.ProgradeHold,_=>FlightAssistMode.Manual};
                    // We exercise contention and repeated assist changes without accumulating unbounded spin.
                    FlightInput first=new(250,13,-11,7,cycle<2?100:-100,23,-31);
                    FlightInput second=cycle is 0 or 1?new(400,-17,11,-7,80,-30,40):new(100,0,0,0,0,0,0);
                    sequence++;
                    p1=[new(sequence,127,first,assist)];p2=[new(sequence,127,second,assist)];
                }
                SharedFrame commands=new(frame,new(frame,p1),new(frame,p2));
                long started=Stopwatch.GetTimestamp();
                SharedSession candidate=shared.Candidate(commands);
                byte[] bytes=candidate.Canonical();lastHash=SharedSession.Hash(bytes);
                byte[] view=JsonSerializer.SerializeToUtf8Bytes(candidate.ViewForReference("399"));lastViewBytes=view.Length;
                shared=candidate;
                double milliseconds=Stopwatch.GetElapsedTime(started).TotalMilliseconds;
                if(i>=warmup)elapsed[i-warmup]=milliseconds;
            }
            double[] sorted=elapsed.Order().ToArray();
            double Quantile(double q)=>sorted[Math.Clamp((int)Math.Ceiling(q*count)-1,0,count-1)];
            double maxWindow=Enumerable.Range(0,count/64).Select(w=>elapsed.Skip(w*64).Take(64).Sum()).Max();
            var receipt=new{schema="precision-full-session-timing-v1",substeps=1<<power,workload,warmup_ticks=warmup,measured_ticks=count,
                runtime=RuntimeInformation.FrameworkDescription,architecture=RuntimeInformation.ProcessArchitecture.ToString(),os=RuntimeInformation.OSDescription,
                mean_ms=elapsed.Average(),p95_ms=Quantile(.95),p99_ms=Quantile(.99),p999_ms=Quantile(.999),max_ms=sorted[^1],
                over_budget_ticks=elapsed.Count(x=>x>15.625),max_64_tick_work_ms=maxWindow,
                cpu_headroom_gate=elapsed.Average()<=12.5 && Quantile(.99)<=12.5,qualification_length=count>=8192,
                lastHash,lastViewBytes,
                scope="single peer Candidate clone/restore, coupled 11-body dynamics, full canonical serialization and SHA256, reference-view calculation and JSON serialization every tick; excludes GPU, transport wait and evidence disk IO"};
            File.WriteAllText(Path.Combine(output,workload+"-timings.json"),JsonSerializer.Serialize(elapsed));
            string json=JsonSerializer.Serialize(receipt,new JsonSerializerOptions{WriteIndented=true});
            File.WriteAllText(Path.Combine(output,workload+".json"),json);Console.WriteLine(json);
        }
    }
}
