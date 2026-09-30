using System.Globalization;
using System.Text.Json;
using Flight.Core;

internal static class Observations
{
    private static string Number(decimal value) => value.ToString("G29", CultureInfo.InvariantCulture);
    internal static string[] Position(KinematicState state) => Enumerable.Range(0,3).Select(i => Number(
        state.PositionMm[i] / 1000m + state.PositionRemainder[i] / (decimal)FlightUnits.PositionRemainderDenominator / 1000m)).ToArray();
    internal static string[] Velocity(KinematicState state) => Enumerable.Range(0,3).Select(i => Number(
        state.VelocityNmPerSec[i] / 1_000_000_000m + state.VelocityRemainder[i] / (decimal)FlightUnits.VelocityRemainderDenominator / 1_000_000_000m)).ToArray();
    internal static string Mass(VesselState v) => Number(v.Profile.DryMassGrams / 1000m + v.PropellantMicrograms / 1_000_000_000m
        - v.MainFuelRemainder / (128m * v.Profile.MainExhaustVelocityMmPerSec) / 1_000_000_000m
        - (decimal)v.RcsFuelRemainder / (128m * v.Profile.RcsExhaustVelocityMmPerSec * v.Profile.RcsLeverArmMm) / 1_000_000_000m);

    internal static string Initial(string name, FlightState s) => JsonSerializer.Serialize(new
    {
        schema = "qualification-initial-v1", @case = name, steps_per_second = s.StepsPerSecond, integration_substeps=1<<s.IntegrationSubstepPower,
        duration_seconds = Fixtures.Seconds(name), sample_interval_seconds = 1,
        bodies = s.Bodies.Select(b => new { id=b.Id, gm_m3_s2=Number((decimal)b.GmMicroM3PerS2/1_000_000m), radius_m=Number(b.RadiusMm/1000m), p=Position(b), v=Velocity(b) }),
        vessel = new { id=s.Vessel.Id, p=Position(s.Vessel), v=Velocity(s.Vessel), mass_kg=Mass(s.Vessel),
            dry_mass_kg=Number(s.Vessel.Profile.DryMassGrams/1000m), thrust_n=name=="inertial-burn" ? "1000" : "0", exhaust_velocity_m_s=Number(s.Vessel.Profile.MainExhaustVelocityMmPerSec/1000m) },
        burn = new { start_seconds=0, end_seconds=name=="inertial-burn" ? 60 : 0, force_direction=new[]{1,0,0} },
        observation_precision = "decimal display projection; complete canonical authority retained separately",
        frame = name=="lunar-fixture" ? "barycentric-ecliptic-j2000" : "isolated-inertial",
        epoch_tdb = "2207-01-01T00:00:00"
    });

    internal static string Sample(FlightState s) => JsonSerializer.Serialize(new
    {
        tick=s.Tick, time_s=s.Tick/(decimal)s.StepsPerSecond,
        bodies=s.Bodies.Select(b=>new{id=b.Id,p=Position(b),v=Velocity(b)}),
        vessel=new{p=Position(s.Vessel),v=Velocity(s.Vessel),mass_kg=Mass(s.Vessel)}
    });
}
