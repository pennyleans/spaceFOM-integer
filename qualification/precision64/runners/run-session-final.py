from pathlib import Path
import hashlib,json,os,platform,subprocess
root=Path(__file__).resolve().parent
runtime=os.environ.get('DOTNET_EXE','dotnet')
dll=root/'probe/bin/Release/net10.0/Flight.Session.Tests.dll'
out=root/'results/session-final'
assert not out.exists()
rows=[]
for mode,expected in [('session',0),('interrupt',23),('resume',0)]:
    log=root/'results'/('session-final-'+mode+'.log')
    with log.open('w') as f:
        result=subprocess.run([runtime,str(dll),mode,'3',str(root/'source/data'),str(out)],stdout=f,stderr=subprocess.STDOUT,timeout=120)
    row={'mode':mode,'exit':result.returncode,'expected':expected}
    rows.append(row);print(json.dumps(row),flush=True)
    assert result.returncode==expected
(out/'execution.json').write_text(json.dumps({'architecture':platform.machine(),'probe_sha256':hashlib.sha256(dll.read_bytes()).hexdigest(),'rows':rows},indent=2)+'\n')
