"""Offline regression and differential checks; never starts or contacts a game."""
import json
from pathlib import Path
import random
import pickle
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from mechanics import Kernel, LAB, NAMES

SOURCE=LAB.parents[1]/'work/installed-source'
DLL=Path(r'D:\download\SteamGame\steamapps\common\Balatro\lua51.dll')

def card(rank,suit='Hearts',**kw): return dict(rank=rank,suit=suit,**kw)

class KernelTests(unittest.TestCase):
    def setUp(self): self.k=Kernel(SOURCE,DLL)
    def tearDown(self): self.k.close()

    def test_four_fingers_separate_flush_and_straight(self):
        cards=[card(2),card(3),card(4),card(9),card(5,'Clubs')]
        self.assertEqual(self.k.classify(cards,['Four Fingers']),
            {'hand':'Straight Flush','scoring_indices':[0,1,2,3,4]})
        self.assertEqual(self.k.classify(cards)['hand'],'High Card')

    def test_wild_debuff_and_joker_debuff(self):
        cards=[card(2),card(4),card(7),card(9),card(13,'Spades',wild=True)]
        self.assertEqual(self.k.classify(cards)['hand'],'Flush')
        cards[-1]['debuff']=True
        self.assertEqual(self.k.classify(cards)['hand'],'High Card')
        self.assertEqual(self.k.classify(cards,[{'name':'Four Fingers','debuff':True}])['hand'],'High Card')
        self.assertEqual(self.k.classify(cards,['Four Fingers'])['hand'],'Flush')

    def test_seed_stream_reset_and_runtime_isolation(self):
        self.k.reset('FIXTURE')
        first=[self.k.pseudoseed('shop') for _ in range(3)]
        with Kernel(SOURCE,DLL) as other:
            other.reset('UNRELATED')
            other.pseudoseed('shop')
            self.k.reset('FIXTURE')
            self.assertEqual(first,[self.k.pseudoseed('shop') for _ in range(3)])
        self.k.reset('FIXTURE')
        one=self.k.pseudoseed('shop'); self.k.pseudoseed('pack')
        self.assertEqual([one,self.k.pseudoseed('shop')],first[:2])
        with self.assertRaises(ValueError): self.k.pseudoseed('seed')

    def test_blind_scaling_and_fail_closed(self):
        self.assertEqual([self.k.blind_amount(i) for i in range(1,9)],
                         [300,1000,3200,9000,25000,60000,110000,200000])
        with self.assertRaises(ValueError): self.k.classify([card(2,stone=True)])
        with self.assertRaises(ValueError): self.k.classify([card(2)],['Blueprint'])

    def test_native_handle_cannot_cross_worker_boundary(self):
        with self.assertRaises(TypeError): pickle.dumps(self.k)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.assertRaises(RuntimeError): pool.submit(self.k.pseudoseed,'shop').result()
        self.assertIsInstance(self.k.pseudoseed('shop'),float)

    def test_standard_cards_against_independent_python_classifier(self):
        sys.path.insert(0,str(LAB/'cli'))
        sys.path.insert(0,str(LAB/'experiments/policies/route_v2'))
        import advisor
        rng=random.Random(939); count=0; started=time.perf_counter()
        for ff in (False,True):
            for shortcut in (False,True):
                for smeared in (False,True):
                    for _ in range(250):
                        ids=rng.sample(range(52),rng.randint(1,5))
                        cs=[card(i%13+2,['Spades','Hearts','Clubs','Diamonds'][i//13]) for i in ids]
                        names=[n for n,enabled in zip(['Four Fingers','Shortcut','Smeared Joker'],[ff,shortcut,smeared]) if enabled]
                        actual=self.k.classify(cs,names)
                        inputs=[{'value':{'rank':'23456789TJQKA'[i%13],'suit':'SHCD'[i//13]},'modifier':{},'state':{}} for i in ids]
                        cat,scored,_=advisor.classify(inputs,range(len(ids)),ff,shortcut,smeared)
                        self.assertEqual(actual['hand'],NAMES[cat])
                        # High-card ties use physical nominal/suit in original Lua;
                        # Python's simplified classifier may choose another equal rank.
                        if cat: self.assertEqual(sorted(actual['scoring_indices']),sorted(scored))
                        count+=1
        elapsed=time.perf_counter()-started
        (Path(__file__).parent/'verification.json').write_text(json.dumps({
            'differential_cases':count,'seconds':elapsed,'includes_python_oracle':True,
            'source_sha256':self.k.hashes,'scope':'classification, pseudoseed, blind amount; no complete runs',
            'high_card_tie_indices_compared':False},indent=2),encoding='utf-8')

if __name__=='__main__': unittest.main()
