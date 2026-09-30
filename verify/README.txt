2207: Integer Spaceflight Simulator - replay verification

2207-verify reruns five orbital scenarios and a scripted 16-second session,
hashes the complete simulation state at every 64 Hz tick, and compares the
result with the hashes in expected.json. Those hashes were recorded on
x86-64 Windows and AArch64 macOS. A match means this machine produced the
same 1,497,350 states bit for bit.

Run from this folder:

  2207-verify.exe                (Windows)
  ./2207-verify                  (macOS, Linux)

Options:
  --quick             run three short checks (under a minute)
  --receipt <file>    also write the results as JSON

A full run takes a few minutes and uses one core per scenario. Exit code 0
means every hash matched; 1 means at least one differed.

The package is self-contained and needs no .NET installation. On macOS it
is a folder with the executable and the runtime libraries beside it; on other
platforms it is a single executable. data/ holds the body catalogue and
vessel definition the scenarios use. LICENSE and NOTICE give the terms of the
verifier; licenses/dotnet/ holds the licence and notices of the bundled .NET
runtime.

macOS: the executable carries an ad-hoc signature but is not notarized. If
macOS blocks it, clear the download attribute from the whole folder:
  xattr -dr com.apple.quarantine .
Do not re-sign the files.
