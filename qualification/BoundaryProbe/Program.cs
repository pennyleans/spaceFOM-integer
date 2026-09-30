using System.Text.Json;
using Flight.Core;
using Flight.Data;
using Flight.Guidance;
using Flight.SpaceFom;

if (args.Length != 2 || Directory.Exists(args[1])) throw new ArgumentException("<private-data> <fresh-output>");
Directory.CreateDirectory(args[1]);
SimulationSession session = Fixtures.Lunar(args[0]);
for (int tick = 0; tick < 32; tick++) session.Step(new(100, 2, 3, 4, 1, 2, 3));
FlightSessionSnapshot accepted = session.Capture();
byte[] before = SessionCodec.Encode(accepted);
List<string> rejected = [];
void Refuse(string name, Action attempt)
{
    bool refused = false;
    try { attempt(); }
    catch (Exception error) when (error is InvalidDataException or JsonException or FlightFault) { refused = true; }
    if (!refused || !before.AsSpan().SequenceEqual(SessionCodec.Encode(session.Capture())))
        throw new Exception("rejected restore changed live state: " + name);
    rejected.Add(name);
}
Refuse("truncated bytes at decode boundary", () => session.Restore(SessionCodec.Decode(before[..^1])));
Refuse("invalid decoded physical attitude", () => session.Restore(SessionCodec.Decode(SessionCodec.Encode(
    accepted with { Physical = accepted.Physical with { Vessel = accepted.Physical.Vessel with { Attitude = new(1,0,0,0) } } }))));
Refuse("duplicate decoded vessel and body id", () => session.Restore(SessionCodec.Decode(SessionCodec.Encode(
    accepted with { Physical = accepted.Physical with { Vessel = accepted.Physical.Vessel with { Motion = accepted.Physical.Vessel.Motion with { Id = "399" } } } }))));
Refuse("invalid decoded guidance target", () => session.Restore(SessionCodec.Decode(SessionCodec.Encode(
    accepted with { Guidance = accepted.Guidance with { Mode = GuidanceMode.AttitudeHold, HasTargetAttitude = false, TargetAttitude = default } }))));

// We use the exact 120-degree cyclic-axis rotation: body x -> parent y, body y -> parent z, body z -> parent x.
VesselState vessel = Fixtures.Lunar(args[0]).State.Vessel;
vessel.PositionMm = new(1250,-2500,3750);
vessel.PositionRemainder = default;
vessel.VelocityNmPerSec = new(4_000_000_000,-8_000_000_000,16_000_000_000);
vessel.VelocityRemainder = default;
vessel.Attitude = new(FixedQuaternion.Scale/2,FixedQuaternion.Scale/2,FixedQuaternion.Scale/2,FixedQuaternion.Scale/2);
vessel.AngularVelocityNradPerSec = new(125_000_000,-250_000_000,500_000_000);
vessel.AngularVelocityRemainder = default;
byte[] bytes = WireState.From(vessel,64).Encode();
double[] expected = [1.25,-2.5,3.75,4,-8,16,0.5,-0.5,-0.5,-0.5,0.125,-0.25,0.5,7529673601.00018];
for(int i=0;i<expected.Length;i++)
    if(BitConverter.ToInt64(bytes,i*8)!=BitConverter.DoubleToInt64Bits(expected[i]))
        throw new Exception("wire meaning or sign differs at field " + i);
// We derive the passive direction directly: parent x becomes body z for this cyclic-axis rotation.
double w=expected[6], x=expected[7], y=expected[8], z=expected[9];
double[] mappedParentX=[1-2*(y*y+z*z),2*(x*y+w*z),2*(x*z-w*y)];
if(!mappedParentX.SequenceEqual(new double[]{0,0,1})) throw new Exception("passive rotation direction differs");
File.WriteAllBytes(Path.Combine(args[1],"mapped-state.bin"),bytes);
// We also use distinct quaternion components so a field-order swap cannot hide in a symmetric rotation.
vessel.Attitude = new(FixedQuaternion.Scale/11,2*FixedQuaternion.Scale/11,4*FixedQuaternion.Scale/11,checked((long)((Int128)10*FixedQuaternion.Scale/11)));
WireState asymmetric = WireState.From(vessel,64);
double[] asymmetricExpected = [1.0/11,-2.0/11,-4.0/11,-10.0/11];
for(int i=0;i<4;i++)
    if(Math.Abs(asymmetric.Values[6+i]-asymmetricExpected[i])>1e-15) throw new Exception("asymmetric quaternion differs");
w=asymmetric.Values[6];x=asymmetric.Values[7];y=asymmetric.Values[8];z=asymmetric.Values[9];
double[] transformed=[1-2*(y*y+z*z),2*(x*y+w*z),2*(x*z-w*y)];
double[] transformedExpected=[-111.0/121,-4.0/121,48.0/121];
for(int i=0;i<3;i++)
    if(Math.Abs(transformed[i]-transformedExpected[i])>1e-15) throw new Exception("asymmetric passive basis differs");
File.WriteAllBytes(Path.Combine(args[1],"asymmetric-mapped-state.bin"),asymmetric.Encode());
File.WriteAllText(Path.Combine(args[1],"receipt.json"),JsonSerializer.Serialize(new {
    schema="qualification-boundary-v1", decoded_restore_rejections=rejected, complete_live_bytes_preserved=true,
    mapped_wire_fields=14, bitwise_expected_fields_equal=true, parent_x_maps_to_body_z=true,
    asymmetric_parent_x_expected=transformedExpected, asymmetric_parent_x_observed=transformed, asymmetric_tolerance=1e-15,
    scope="supplemental Windows x64 decoded-domain restore and known cyclic quaternion/units/time projection; no general frame or 2207 clock accuracy claim"
},new JsonSerializerOptions{WriteIndented=true}));
Console.WriteLine("pass: four rejection boundaries preserve complete live bytes; fourteen mapped wire fields match exact expected bits");
