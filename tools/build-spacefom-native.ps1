param([string]$TransportRoot = (Join-Path $PSScriptRoot '../out/transport'))
$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path -Parent $PSScriptRoot
$rtiRevision = '6e31e0cd50de1852813a98679e8731ad2c97e54b'
$fomRevision = '9faa0c5e547acb2596047c9bb875cb34ccb0fa2a'
New-Item -ItemType Directory -Force -Path $TransportRoot | Out-Null
function Invoke-Native([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed with $LASTEXITCODE" }
}
if (!(Test-Path -LiteralPath "$TransportRoot\OpenRTI\.git")) {
    Invoke-Native git @('clone','https://git.code.sf.net/p/openrti/OpenRTI',"$TransportRoot\OpenRTI")
    Invoke-Native git @('-C',"$TransportRoot\OpenRTI",'checkout','--detach',$rtiRevision)
}
if ((git -C "$TransportRoot\OpenRTI" rev-parse HEAD) -ne $rtiRevision) { throw 'OpenRTI revision mismatch' }
if ((git -C "$TransportRoot\OpenRTI" status --porcelain)) { throw 'OpenRTI source is modified' }
if (!(Test-Path -LiteralPath "$TransportRoot\TrickHLA\.git")) {
    Invoke-Native git @('clone','--filter=blob:none','--sparse','https://github.com/nasa/TrickHLA.git',"$TransportRoot\TrickHLA")
    Invoke-Native git @('-C',"$TransportRoot\TrickHLA",'checkout','--detach',$fomRevision)
    Invoke-Native git @('-C',"$TransportRoot\TrickHLA",'sparse-checkout','set','FOMs/SpaceFOM')
}
if ((git -C "$TransportRoot\TrickHLA" rev-parse HEAD) -ne $fomRevision) { throw 'FOM source revision mismatch' }
if ((git -C "$TransportRoot\TrickHLA" status --porcelain)) { throw 'FOM source is modified' }
Invoke-Native cmake @('-S',"$TransportRoot\OpenRTI",'-B',"$TransportRoot\openrti-build",'-G','Visual Studio 17 2022','-A','x64','-DOPENRTI_ENABLE_RTI13=OFF','-DOPENRTI_ENABLE_RTI1516=OFF','-DOPENRTI_ENABLE_PYTHON_BINDINGS=OFF',"-DCMAKE_INSTALL_PREFIX=$TransportRoot/runtime")
Invoke-Native cmake @('--build',"$TransportRoot\openrti-build",'--config','Release','--parallel','6','--target','INSTALL')
Invoke-Native cmake @('-S',"$sourceRoot\native\spacefom",'-B',"$TransportRoot\adapter-build",'-G','Visual Studio 17 2022','-A','x64',"-DOPENRTI_ROOT=$TransportRoot/runtime")
Invoke-Native cmake @('--build',"$TransportRoot\adapter-build",'--config','Release','--parallel','4')
Write-Output "native executables: $TransportRoot\adapter-build\Release"
Write-Output "runtime remains separate: $TransportRoot\runtime\bin"
