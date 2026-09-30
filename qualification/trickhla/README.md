# TrickHLA interop observer

`input-latejoin.py` is the working configuration: it sets the subscribed PhysicalEntity's instance and parent frame names, which TrickHLA requires, and turns lag compensation off. Build the simulation with a data cycle of 1/64 s to match our least common time step. `input.py` is the first version and stops on the missing entity name.

This directory holds the TrickHLA configuration for the 2207 interoperability
test. `input.py` configures the TrickHLA federate that joins our exchange
federation as the "other" role:

- Federation `orbital_8989`, federate `orbital_other`, both overridable on the
  command line.
- Not Master, not Pacing, not Root Reference Frame Publisher.
- Required federates `orbital_master` and `orbital_observer`.
- The same five SISO SpaceFOM modules as our publisher, from the pinned
  TrickHLA revision.
- Subscriptions: the root frame `SolarSystemBarycentricInertial`, one body
  frame (`body_10`), and the `orbital_vessel` PhysicalEntity.

To run it, copy `input.py` into a new run directory of a built SpaceFOM
simulation that defines `root_ref_frame`, `leaf_ref_frame`, `physical_entity`
and the `THLA` SimObjects (`sims/SpaceFOM/SIM_Entity_Test` provides all of
them), then execute:

```
./S_main_Linux_*.exe RUN_interop/input.py --verbose on \
  --crc_host <crc host> --crc_port 8989
```

Known limits of this configuration, described in the report:

- The stock simulation defines only two reference frame packings, so this file
  subscribes to the root frame and one body frame. Subscribing to all eleven
  body frames needs one additional frame packing per body in the sim
  definition.
- Logging the object name, the HLA logical time and the fourteen decoded state
  values at every received update needs a compiled override of the SpaceFOM
  packing `unpack()` methods. The configuration here turns on TrickHLA trace
  logging instead.
- The Pitch pRTI Free edition states that it supports no more than two
  federates. The three-federate exchange is described in the report.
