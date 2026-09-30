2207: Integer Spaceflight Simulator - SpaceFOM exchange

Runs an HLA exchange on this machine: an OpenRTI server, a publisher that
sends a recorded 60-second lunar coast through the SpaceFOM data model, and
an observer that rebuilds the recording from RTI callbacks alone. The run
includes a coordinated freeze, resume and shutdown, then compares the sent
and received files.

Run from this folder:

  pwsh ./run-exchange.ps1        (or powershell .\run-exchange.ps1 on Windows)

Success prints "byte_identity: True". Results and logs go to runs/.
Options: -Recording <file.sf>, -Output <new directory>, -Port <number>.

Everything runs on 127.0.0.1 and needs no network access. Windows needs the
Microsoft Visual C++ 2015-2022 x64 runtime.

Contents:
  bin/          publisher, observer, OpenRTI server and libraries
  fom/          the five SISO SpaceFOM modules, unmodified
  recordings/   the recording, ICRF axes, 3,841 frames at 64 Hz
  licenses/     OpenRTI, Expat and SISO notices; LICENSE and NOTICE cover the adapter
  source/       the unmodified OpenRTI source used for these binaries
