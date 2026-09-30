using Flight.Core;
using Flight.Data;

internal static class Fixtures
{
    internal static SimulationSession Lunar(string data) => new(
        SolarCatalog.Load(Path.Combine(data, "sol-2207.json")),
        ShipLoader.Load(Path.Combine(data, "ships/reference-tug.ship.toml"), Path.Combine(data, "ships/reference-tug.flight.json")),
        intentIdentity: "spacefom-neutral-coast-v1", startBodyId: "301", startAltitudeMm: 100_000_000);

    internal static int Seconds(string name) => name switch
    {
        "earth-orbit" => 6000, "moon-orbit" => 7200, "inertial-burn" => 120,
        "lunar-fixture" => 60, _ => throw new ArgumentException("unknown fixture")
    };

    internal static FlightState Create(string name, int rate, string data)
    {
        if (rate is not (64 or 128)) throw new ArgumentException("unsupported qualification rate");
        if (name == "lunar-fixture")
        {
            FlightState source = Lunar(data).State;
            return new(source.Bodies, source.Vessel, rate) { ContentIdentity = source.ContentIdentity };
        }
        FlightProfile profile = new("qualification-fixture-v1", 12_000_000, 6_000_000, 1_000_000,
            4_500_000, 0, 4_500_000, 0, 1000, new(1000,1000,1000), new(1000,1000,1000), 1);
        if (name == "inertial-burn")
        {
            // We retain a positive distant source for the snapshot domain; its acceleration rounds to zero.
            BodyState distant = new("distant", new(1_000_000_000_000_000,0,0), default, 1, 1);
            return new([distant], new("fixture", default, default, profile), rate) { ContentIdentity = "qualification/inertial-burn-v1" };
        }
        long radiusM = name == "earth-orbit" ? 6_778_137 : 1_837_400;
        long mu = name == "earth-orbit" ? 398_600_435_507_000 : 4_902_800_066_000;
        long bodyRadiusMm = name == "earth-orbit" ? 6_378_137_000 : 1_737_400_000;
        long speedNm = checked((long)Math.Round(Math.Sqrt(mu / (double)radiusM) * 1e9));
        BodyState primary = new(name == "earth-orbit" ? "399" : "301", default, default, (Int128)mu * 1_000_000, bodyRadiusMm);
        VesselState vessel = new("fixture", new(radiusM * 1000,0,0), new(0,speedNm,0), profile);
        return new([primary], vessel, rate) { ContentIdentity = "qualification/" + name + "-v1" };
    }

    internal static FlightCommand Command(string name, long tick, int rate) =>
        name == "inertial-burn" && tick < 60L * rate ? new(0,0,0,0,0,0,1000) : default;
}
