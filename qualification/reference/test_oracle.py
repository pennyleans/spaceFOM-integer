"""Reference self-tests use closed identities and no simulation implementation."""
import math
import unittest
from decimal import Decimal
from oracle import kepler, norm, sub, rocket, rk4_reference


class ReferenceTests(unittest.TestCase):
    def test_circle_full_quarter_and_reverse(self):
        r,mu=7000000.0,398600435507000.0
        speed=math.sqrt(mu/r)
        period=2*math.pi*math.sqrt(r**3/mu)
        p,v=kepler([r,0,0],[0,speed,0],mu,period/4)
        self.assertLess(norm(sub(p,[0,r,0])),1e-7)
        self.assertLess(norm(sub(v,[-speed,0,0])),1e-10)
        p,v=kepler(p,v,mu,-period/4)
        self.assertLess(norm(sub(p,[r,0,0])),1e-7)
        p,v=kepler([r,0,0],[0,speed,0],mu,period)
        self.assertLess(norm(sub(p,[r,0,0])),1e-7)

    def test_eccentric_periapsis_to_apoapsis(self):
        a,e,mu=10000000.0,0.6,398600435507000.0
        rp=a*(1-e)
        vp=math.sqrt(mu*(1+e)/rp)
        period=2*math.pi*math.sqrt(a**3/mu)
        p,v=kepler([rp,0,0],[0,vp,0],mu,period/2)
        self.assertLess(norm(sub(p,[-a*(1+e),0,0])),1e-6)
        self.assertLess(norm(sub(v,[0,-vp*(1-e)/(1+e),0])),1e-9)

    def test_half_mass_rocket_then_coast(self):
        initial={'vessel':{'p':['0']*3,'v':['0']*3,'mass_kg':'2','dry_mass_kg':'1','thrust_n':'1','exhaust_velocity_m_s':'1'},'burn':{'start_seconds':0,'end_seconds':1,'force_direction':[1,0,0]}}
        p,v,m=rocket(initial,2)
        self.assertAlmostEqual(v[0],math.log(2),places=14)
        self.assertAlmostEqual(p[0],1.0,places=7)
        self.assertEqual(m,1)

    def test_rk4_refines_toward_circle(self):
        initial={'bodies':[{'id':'root','p':['0']*3,'v':['0']*3,'gm_m3_s2':'1'}],'vessel':{'id':'probe','p':['1','0','0'],'v':['0','1','0'],'thrust_n':'0'}}
        errors=[]
        exact=[math.cos(1),math.sin(1),0]
        for h in (0.1,0.05):
            _,out=rk4_reference(initial,[0,1],h)
            errors.append(norm(sub(out[-1][-6:-3],exact)))
        self.assertLess(errors[1]/errors[0],0.1)

    def test_reference_is_invariant_under_barycentric_translation_and_boost(self):
        initial={'bodies':[{'id':'root','p':['0']*3,'v':['0']*3,'gm_m3_s2':'1'}],'vessel':{'id':'probe','p':['1','0','0'],'v':['0','1','0'],'thrust_n':'0'}}
        _,base=rk4_reference(initial,[0,1],0.01)
        for item in initial['bodies']+[initial['vessel']]:
            item['p']=[str(Decimal(x)+Decimal('1000000000000000')) for x in item['p']]
            item['v']=[str(Decimal(x)+Decimal('30000')) for x in item['v']]
        _,shifted=rk4_reference(initial,[0,1],0.01)
        self.assertEqual(base,shifted)


if __name__=='__main__':
    unittest.main()
