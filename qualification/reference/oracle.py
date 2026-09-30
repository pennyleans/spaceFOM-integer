"""Independent, stdlib-only numerical qualification reference; no core imports."""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import platform
import sys


def norm(v):
    return math.sqrt(math.fsum(x*x for x in v))


def sub(a, b):
    return [x-y for x, y in zip(a, b)]


def dot(a, b):
    return math.fsum(x*y for x, y in zip(a, b))


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(a, b):
    # Subtract decimal positions before conversion to avoid barycentric cancellation.
    return [float(Decimal(str(x))-Decimal(str(y))) for x, y in zip(a, b)]


def stumpff(z):
    if abs(z) < 1e-6:
        c, s = 0.0, 0.0
        for k in range(8):
            c += (-z)**k / math.factorial(2*k+2)
            s += (-z)**k / math.factorial(2*k+3)
        return c, s
    if z > 0:
        x = math.sqrt(z)
        return 2*math.sin(x/2)**2/z, (x-math.sin(x))/(x*x*x)
    x = math.sqrt(-z)
    return (math.cosh(x)-1)/(-z), (math.sinh(x)-x)/(x*x*x)


def kepler(p, v, mu, t):
    """Universal-variable two-body f/g solution, independent of integration."""
    if t == 0:
        return list(p), list(v)
    r0 = norm(p)
    root_mu = math.sqrt(mu)
    rv = dot(p, v) / root_mu
    alpha = 2/r0 - dot(v, v)/mu
    chi = root_mu*t*abs(alpha) if abs(alpha) > 1e-15 else root_mu*t/r0
    for _ in range(100):
        z = alpha*chi*chi
        c, s = stumpff(z)
        f = rv*chi*chi*c + (1-alpha*r0)*chi**3*s + r0*chi-root_mu*t
        df = rv*chi*(1-z*s) + (1-alpha*r0)*chi*chi*c + r0
        delta = f/df
        chi -= delta
        if abs(delta) <= 1e-12*max(1.0, abs(chi)):
            break
    else:
        raise ArithmeticError("universal anomaly did not converge")
    z = alpha*chi*chi
    c, s = stumpff(z)
    f = 1-chi*chi*c/r0
    g = t-chi**3*s/root_mu
    pos = [f*x+g*y for x, y in zip(p, v)]
    r = norm(pos)
    fdot = root_mu/(r*r0)*(alpha*chi**3*s-chi)
    gdot = 1-chi*chi*c/r
    vel = [fdot*x+gdot*y for x, y in zip(p, v)]
    return pos, vel


def rocket(initial, t):
    """Exact constant inertial thrust, constant exhaust speed, linear mass loss."""
    vessel, burn = initial['vessel'], initial['burn']
    m0, thrust, ve = (float(vessel[k]) for k in ('mass_kg','thrust_n','exhaust_velocity_m_s'))
    start, end = float(burn['start_seconds']), float(burn['end_seconds'])
    tau = min(max(t-start, 0.0), end-start)
    mdot = thrust/ve
    m = m0-mdot*tau
    if m < float(vessel['dry_mass_kg']):
        raise ValueError('oracle burn would cross dry mass')
    x = mdot*tau/m0
    dv = -ve*math.log1p(-x)
    # x + (1-x)*log(1-x) = sum x^n/(n*(n-1)); avoids short-burn cancellation.
    displacement = ve*m0/mdot*math.fsum(x**n/(n*(n-1)) for n in range(2, 24)) if mdot else 0.0
    displacement += dv*max(t-end, 0.0)
    d = [float(a) for a in burn['force_direction']]
    if abs(norm(d)-1) > 1e-14:
        raise ValueError('burn direction must be unit length')
    p = [float(a)+float(b)*t+c*displacement for a,b,c in zip(vessel['p'],vessel['v'],d)]
    v = [float(a)+b*dv for a,b in zip(vessel['v'],d)]
    with localcontext() as ctx:
        ctx.prec = 60
        exact_mass = Decimal(vessel['mass_kg'])-Decimal(vessel['thrust_n'])/Decimal(vessel['exhaust_velocity_m_s'])*Decimal(str(tau))
    return p, v, exact_mass


def anchor(initial):
    vessel = initial['vessel']
    return min(initial['bodies'], key=lambda b: norm(relative(vessel['p'], b['p'])))


def shifted(record, origin, t):
    return ([float(Decimal(str(x))-Decimal(str(o))-Decimal(str(u))*Decimal(str(t))) for x,o,u in zip(record['p'],origin['p'],origin['v'])], relative(record['v'],origin['v']))


def rk4_reference(initial, times, step, residuals=False):
    """RK4 deviations from each object's initial rectilinear path.

    Integrating small deviations avoids adding tiny increments to outer-planet
    coordinates. Initial coordinate differences are formed in decimal first.
    """
    if float(initial['vessel']['thrust_n']) != 0:
        raise ValueError('multibody reference is a coast reference')
    origin = anchor(initial)
    objects = initial['bodies']+[initial['vessel']]
    mus = [float(b['gm_m3_s2']) for b in initial['bodies']]+[0.0]
    base = [z for obj in objects for vector in shifted(obj, origin, 0) for z in vector]
    state = [0.0]*len(base)
    count = len(objects)
    initial_differences={}
    for i in range(count):
        for j in range(count-1):
            if i!=j:
                initial_differences[i,j]=(relative(objects[j]['p'],objects[i]['p']),relative(objects[j]['v'],objects[i]['v']))

    def rhs(y,t):
        result = []
        for i in range(count):
            a = [0.0,0.0,0.0]
            for j in range(count-1):
                if i == j:
                    continue
                dp,dv=initial_differences[i,j]
                d = [dp[k]+dv[k]*t+y[6*j+k]-y[6*i+k] for k in range(3)]
                r = norm(d)
                factor = mus[j]/(r*r*r)
                for k in range(3):
                    a[k] += d[k]*factor
            result.extend(y[6*i+3:6*i+6]+a)
        return result

    current = 0.0
    output = []
    for target in times:
        while current < target-1e-12:
            h = min(step,target-current)
            k1=rhs(state,current)
            k2=rhs([y+h*a/2 for y,a in zip(state,k1)],current+h/2)
            k3=rhs([y+h*a/2 for y,a in zip(state,k2)],current+h/2)
            k4=rhs([y+h*a for y,a in zip(state,k3)],current+h)
            state = [y+h*(a+2*b+2*c+d)/6 for y,a,b,c,d in zip(state,k1,k2,k3,k4)]
            current += h
        if residuals:
            output.append(list(state))
        else:
            output.append([base[k]+(base[k+3]*current if k%6<3 else 0.0)+state[k] for k in range(len(state))])
    return origin, output


def read_case(folder):
    initial = json.loads((folder/'initial.json').read_text(encoding='utf-8-sig'))
    samples = [json.loads(s) for s in (folder/'samples.jsonl').read_text(encoding='utf-8-sig').splitlines() if s.strip()]
    times = [float(s['time_s']) for s in samples]
    expected=list(range(0,initial['duration_seconds']+1,initial['sample_interval_seconds']))
    if times!=expected or any(s['tick']!=t*initial['steps_per_second'] for s,t in zip(samples,times)):
        raise ValueError('samples must cover every declared sample time and its corresponding tick')
    return initial, samples, times


def assess(folder):
    initial, samples, times = read_case(folder)
    pos_errors, vel_errors, mass_errors, energies, angular = [],[],[],[],[]
    metrics = {}
    if len(initial['bodies']) == 1 and float(initial['vessel']['thrust_n']) == 0:
        model = 'analytic universal-variable two-body'
        body = initial['bodies'][0]
        mu = float(body['gm_m3_s2'])
        p0 = relative(initial['vessel']['p'],body['p'])
        v0 = relative(initial['vessel']['v'],body['v'])
        for sample,t in zip(samples,times):
            p,v = relative(sample['vessel']['p'],sample['bodies'][0]['p']),relative(sample['vessel']['v'],sample['bodies'][0]['v'])
            rp,rv = kepler(p0,v0,mu,t)
            pos_errors.append(norm(sub(p,rp)))
            vel_errors.append(norm(sub(v,rv)))
            energies.append(dot(v,v)/2-mu/norm(p))
            angular.append(norm(cross(p,v)))
        metrics['max_relative_energy_drift'] = max(abs(e/energies[0]-1) for e in energies)
        metrics['max_relative_angular_momentum_drift'] = max(abs(h/angular[0]-1) for h in angular)
        metrics['conservation_pass'] = metrics['max_relative_energy_drift'] < 2e-6 and metrics['max_relative_angular_momentum_drift'] < 2e-6
        max_pos,max_vel=0.1,0.0001
    elif float(initial['vessel']['thrust_n']) > 0:
        model = 'analytic constant inertial thrust rocket'
        if initial['bodies']:
            if len(initial['bodies']) != 1:
                raise ValueError('rocket reference only permits a single negligible source')
            source=initial['bodies'][0]
            distance=norm(relative(initial['vessel']['p'],source['p']))
            mu=float(source['gm_m3_s2'])
            max_a=float(initial['vessel']['thrust_n'])/float(initial['vessel']['dry_mass_kg'])+mu/(distance/2)**2
            travel=norm(relative(initial['vessel']['v'],source['v']))*times[-1]+max_a*times[-1]**2/2
            if travel>=distance/2:
                raise ValueError('cannot bound negligible source with half-distance bootstrap')
            acceleration_bound=mu/(distance-travel)**2
            metrics['neglected_gravity_position_bound_m']=acceleration_bound*times[-1]**2/2
            metrics['neglected_gravity_velocity_bound_m_s']=acceleration_bound*times[-1]
            if metrics['neglected_gravity_position_bound_m']>=1e-12:
                raise ValueError('inertial rocket assumption exceeds declared 1e-12 m negligible-force limit')
        for sample,t in zip(samples,times):
            rp,rv,rm=rocket(initial,t)
            pos_errors.append(norm(sub([float(x) for x in sample['vessel']['p']],rp)))
            vel_errors.append(norm(sub([float(x) for x in sample['vessel']['v']],rv)))
            mass_errors.append(float(abs(Decimal(sample['vessel']['mass_kg'])-rm)))
        metrics['max_mass_error_kg']=max(mass_errors)
        metrics['mass_pass']=metrics['max_mass_error_kg'] < 1e-9
        max_pos,max_vel=0.01,0.0001
    else:
        model = 'independent mutual point-mass RK4, h=0.125 s; refinement h=0.25 s'
        origin,coarse = rk4_reference(initial,times,0.25)
        _,fine=rk4_reference(initial,times,0.125)
        refinement_p,refinement_v=[],[]
        for sample,t,c,f in zip(samples,times,coarse,fine):
            p,v=shifted(sample['vessel'],origin,t)
            pos_errors.append(norm(sub(p,f[-6:-3])))
            vel_errors.append(norm(sub(v,f[-3:])))
            refinement_p.append(norm(sub(c[-6:-3],f[-6:-3])))
            refinement_v.append(norm(sub(c[-3:],f[-3:])))
        metrics['reference_refinement_max_position_m']=max(refinement_p)
        metrics['reference_refinement_max_velocity_m_s']=max(refinement_v)
        metrics['reference_refinement_pass']=max(refinement_p)<0.001 and max(refinement_v)<1e-6
        max_pos,max_vel=0.1,0.0001
    metrics.update(max_position_error_m=max(pos_errors),max_velocity_error_m_s=max(vel_errors),rms_position_error_m=math.sqrt(math.fsum(e*e for e in pos_errors)/len(pos_errors)),final_position_error_m=pos_errors[-1],final_velocity_error_m_s=vel_errors[-1])
    metrics['position_pass']=max(pos_errors)<max_pos
    metrics['velocity_pass']=max(vel_errors)<max_vel
    metrics['pass']=all(value for key,value in metrics.items() if key.endswith('_pass'))
    return {'schema':'independent-reference-receipt-v1','case':initial['case'],'steps_per_second':initial['steps_per_second'],'reference':model,'duration_seconds':times[-1],'sample_count':len(samples),'sample_interval_seconds':initial['sample_interval_seconds'],'complete_declared_sample_coverage':True,'sample_scope':'exported samples only; no assertion about extrema between samples','thresholds':{'max_position_error_m':max_pos,'max_velocity_error_m_s':max_vel,'max_relative_conservation_drift':2e-6,'mass_error_kg':1e-9},'metrics':metrics,'identities':{'initial_sha256':digest(folder/'initial.json'),'samples_sha256':digest(folder/'samples.jsonl'),'oracle_sha256':digest(__file__)},'runtime':{'python':sys.version,'platform':platform.platform()}}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('case_dir',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():
        raise FileExistsError('use a fresh evidence output path')
    result=assess(args.case_dir)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result['metrics'],indent=2))
    return 0 if result['metrics']['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
