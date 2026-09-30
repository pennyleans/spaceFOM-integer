# Third-party notices

| Component | Source | Terms and retained notices |
|---|---|---|
| OpenRTI | SourceForge revision `6e31e0cd50de1852813a98679e8731ad2c97e54b` | The repository licence offers LGPL-2.1, LGPL-3.0 or MPL-2.0; we use MPL-2.0. Keep `LICENSE`, `mpl-2.0.txt`, the source notices and source availability with any binary distribution. The source is unmodified. |
| IEEE 1516-2010 C++ API declarations and standard MIM | Supplied with the same OpenRTI revision | Keep their embedded attribution: "Reprinted with permission from IEEE 1516.1(TM)-2010." |
| Expat XML parser | Bundled with the same OpenRTI revision, `src/OpenRTI/xml` | MIT-style terms; keep the complete notice in `licenses/COPYING-expat` with any distribution. |
| .NET runtime 10.0.12 | Microsoft runtime packs from NuGet, bundled in the self-contained verifier packages | MIT. Each package carries the runtime's `LICENSE.TXT` and `THIRD-PARTY-NOTICES.TXT` under `licenses/dotnet/`. |
| SISO SpaceFOM modules | NASA TrickHLA revision `9faa0c5e547acb2596047c9bb875cb34ccb0fa2a`, `FOMs/SpaceFOM` | Each file carries SISO's schema and API permission, conditional on attribution: "Reprinted with permission from SISO Inc." The embedded notices are preserved. |

Only `SISO_SpaceFOM_datatypes.xml`, `SISO_SpaceFOM_management.xml`, `SISO_SpaceFOM_environment.xml`, `SISO_SpaceFOM_entity.xml` and `SISO_SpaceFOM_switches.xml` are loaded. The NASA Open Source Agreement covering TrickHLA is not substituted for the notices embedded in these five files. Our adapter uses no TrickHLA code or Trick runtime. The interoperability evidence includes logs from TrickHLA federates that were built and run separately; no TrickHLA source is included, and the files in `qualification/trickhla` are our own configuration and override files, applied to a separate TrickHLA checkout.

The adapter links the Microsoft Visual C++ runtime dynamically and expects it to be installed on the machine. The optional Unreal viewer is distributed separately and is not covered by this repository's licence; its redistribution terms are under review.
