import copy,json,sys,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;LAB=HERE.parent
sys.path[:0]=[str(HERE/'policies/route_v2'),str(LAB/'cli'),str(LAB/'scripts')]
import advisor as a
import copying,strategy,phases,consumables
import policy
from belief import Belief,base_deck
from lua_bridge import LuaRuntime

def state():
    for line in (LAB/'results/cli-runs/run-21.jsonl').read_text(encoding='utf-8').splitlines():
        s=json.loads(line).get('result',{})
        if s.get('state')=='SELECTING_HAND':return s

def joker(key,effect='',edition=None):
    return {'key':key,'value':{'effect':effect},'modifier':{'edition':edition} if edition else {},'state':{},'cost':{'sell':2,'buy':4}}

class V2Tests(unittest.TestCase):
    def test_run31_observatory_and_fractional_ramen_observations(self):
        last={};found=set()
        for line in (LAB/'results/cli-runs/run-31.jsonl').read_text(encoding='utf-8').splitlines():
            e=json.loads(line);s=e.get('result',{})
            actual=s.get('round',{}).get('last_hand',{}).get('total')
            if e['method']=='play' and actual in (167031,50489):
                self.assertEqual(a.score(last,e['params']['cards'])[0],actual)
                found.add(actual)
                if actual==167031:
                    without=copy.deepcopy(last);without['used_vouchers']={}
                    self.assertEqual(a.score(without,e['params']['cards'])[0],111354)
                    duplicate=copy.deepcopy(last)
                    duplicate['consumables']['cards'].append(copy.deepcopy(last['consumables']['cards'][0]))
                    self.assertEqual(a.score(duplicate,e['params']['cards'])[0],250547)
            if 'state' in s:last=s
        self.assertEqual(found,{167031,50489})
    def test_ante8_game_over_overrides_engine_won_flag(self):
        import balatro_cli as cli
        self.assertFalse(cli.victory({'state':'GAME_OVER','won':True}))
        self.assertTrue(cli.victory({'state':'ROUND_EVAL','overlay':'win','won':True}))
        self.assertFalse(cli.victory({'state':'SELECTING_HAND','won':False}))
    def test_all_150_real_keys_have_explicit_priors(self):
        self.assertEqual(set(strategy.PRIORS),set(copying.SPECS));self.assertEqual(len(strategy.PRIORS),150)
    def test_all_150_keys_produce_valid_public_state_decisions(self):
        for key in copying.SPECS:
            with self.subTest(key=key):
                s=state();s['jokers']['cards']=[joker(key,' '.join(copying.SPECS[key]['effect_zh']))]
                action=policy.action(s);self.assertIn(action[0],('play','discard','rearrange','sell','use'))
                if action[0] in ('play','discard'):
                    self.assertTrue(1<=len(action[1]['cards'])<=5)
                    self.assertTrue(all(0<=i<len(s['hand']['cards']) for i in action[1]['cards']))
    def test_copy_chains_cycles_and_incompatibility(self):
        cs=[joker(k) for k in ('j_blueprint','j_blueprint','j_joker','j_brainstorm')]
        self.assertEqual([copying.target(cs,i) for i in range(4)],[2,2,2,2])
        cs=[joker('j_blueprint'),joker('j_brainstorm')]
        self.assertEqual([copying.target(cs,i) for i in range(2)],[None,None])
        cs=[joker('j_blueprint'),joker('j_four_fingers')]
        self.assertIsNone(copying.target(cs,0))
    def test_copy_does_not_copy_target_edition(self):
        s=state();s['hand']['cards']=[base_deck()['S_A']];s['jokers']['cards']=[joker('j_blueprint'),joker('j_joker',edition='POLYCHROME')]
        self.assertEqual(a.score(s,[0])[0],216) # 16 * ((1+4+4)*1.5)
    def test_chad_photo_copy_multiplicity(self):
        s=state();s['hand']['cards']=[base_deck()['S_K']]
        s['jokers']['cards']=[joker(k) for k in ('j_blueprint','j_photograph','j_hanging_chad','j_brainstorm')]
        self.assertEqual(a.score(s,[0])[0],17920)
        s['jokers']['cards']=[joker(k) for k in ('j_blueprint','j_hanging_chad','j_photograph','j_brainstorm')]
        self.assertEqual(a.score(s,[0])[0],9600)
    def test_copy_target_switches_between_dna_and_scoring(self):
        s=state();s['jokers']['cards']=[joker(k) for k in ('j_joker','j_blueprint','j_brainstorm','j_dna')]
        action=phases.copy_action(s,'dna');self.assertIsNotNone(action)
        s=phases.reordered(s,action[1]['jokers']);self.assertEqual(copying.count(s,'j_dna'),3)
        self.assertIsNone(phases.copy_action(s,'dna'))
        s['round']['hands_played']=1
        action=phases.copy_action(s,'combat');self.assertIsNotNone(action)
        s=phases.reordered(s,action[1]['jokers']);self.assertEqual(copying.count(s,'j_joker'),3)
        self.assertIsNone(phases.copy_action(s,'combat'))
    def test_income_copy_when_existing_hand_already_wins(self):
        s=state();s['hands']['High Card']['mult']=1000
        s['hand']['cards'][0]['modifier']={'enhancement':'GOLD'}
        s['jokers']['cards']=[joker(k) for k in ('j_blueprint','j_joker','j_mime')]
        action=phases.copy_action(s,'combat');self.assertIsNotNone(action)
        s=phases.reordered(s,action[1]['jokers']);self.assertEqual(copying.count(s,'j_mime'),2)
        self.assertIsNone(phases.copy_action(s,'combat'))
    def test_perkeo_exit_copy_and_template_is_retained(self):
        s=state();s['state']='SHOP';s['jokers']['cards']=[joker(k) for k in ('j_blueprint','j_joker','j_perkeo','j_brainstorm')]
        s['consumables']['cards']=[{'key':'c_cryptid','set':'SPECTRAL'},{'key':'c_pluto','set':'PLANET'}]
        action=phases.copy_action(s,'exit');s=phases.reordered(s,action[1]['jokers'])
        self.assertEqual(copying.count(s,'j_perkeo'),3)
        action=consumables.held_action(s);self.assertEqual(action[1]['consumable'],1)
    def test_mutable_collection_and_hidden_hand(self):
        s=state();s['hand']['cards']=[base_deck()['S_A'],{'key':'HIDDEN','state':{'hidden':True}}]
        ctx={'deck_multiset':[{'card':base_deck()['S_A'],'count':3},{'card':base_deck()['H_K'],'count':1}],
             'visible_discard':[],'visible_hand':[],'probability_normal':1}
        v=Belief().observe(s,ctx)
        self.assertEqual(len(v['_belief']['deck']),4);self.assertEqual(len(v['_belief']['unseen']),3)
        self.assertTrue(v['_belief']['hidden_identity_approximation'])
    def test_death_preserves_rightmost_donor(self):
        s=state();s['hand']['cards'][0]['modifier']={'seal':'BLUE'}
        value,targets,prep=consumables.plan({'key':'c_death'},s)
        self.assertGreater(value,0);self.assertEqual(prep[0],'rearrange')
        s['hand']['cards']=[s['hand']['cards'][i] for i in prep[1]['hand']]
        value,targets,prep=consumables.plan({'key':'c_death'},s)
        self.assertIsNone(prep);self.assertGreater(targets[1],targets[0]);self.assertEqual(s['hand']['cards'][targets[1]]['modifier']['seal'],'BLUE')
    def test_stone_rank_and_hiker_retriggers(self):
        s=state();c=base_deck()['S_2'];c['modifier']={'enhancement':'STONE'};s['hand']['cards']=[c]
        s['jokers']['cards']=[joker('j_fibonacci')];self.assertEqual(a.score(s,[0])[0],55)
        s['hand']['cards']=[base_deck()['S_2']];s['jokers']['cards']=[joker('j_hiker'),joker('j_hanging_chad')]
        self.assertEqual(a.score(s,[0])[0],26) # 5 +(2+0)+(2+5)+(2+10)
    def test_original_lua_three_dna_triggers_from_copy_chain(self):
        source=(LAB.parents[1]/'work/installed-source/card.lua').read_text(encoding='utf-8')
        start=source.index('function Card:calculate_joker(');end=source.index('\nfunction ',start+1)
        with LuaRuntime(r'D:\download\SteamGame\steamapps\common\Balatro\lua51.dll') as lua:
            lua.execute('''Card={};G={jokers={cards={}},hand={emplace=function() end},deck={config={card_limit=52}},
              playing_cards={},GAME={current_round={hands_played=0}},C={CHIPS={},BLUE={},RED={}},E_MANAGER={add_event=function() end}}
              function Event(e) return e end
              function copy_card(c) return {add_to_deck=function() end,states={}} end
              function localize(...) return '' end''')
            lua.execute(source[start:end])
            lua.execute('''for _,name in ipairs({'Blueprint','DNA','Brainstorm'}) do
              local j={ability={set='Joker',name=name},calculate_joker=Card.calculate_joker}
              table.insert(G.jokers.cards,j)
            end
            for _,j in ipairs(G.jokers.cards) do j:calculate_joker({cardarea=G.jokers,before=true,full_hand={{}},poker_hands={}}) end
            assert(#G.playing_cards==3)
            assert(G.deck.config.card_limit==55)''')
    def test_public_context_has_no_order_or_identity(self):
        source=LAB.parents[1]/'work/balatro-source/mods/lab_cli/context.lua'
        with LuaRuntime(r'D:\download\SteamGame\steamapps\common\Balatro\lua51.dll') as lua:
            lua.execute('''local function card(s,r,id) return {base={suit=s,value=r},config={center={key='c_base'}},ability={},sort_id=id} end
            A=card('Spades','Ace',100);K=card('Hearts','King',999);K.facing='back'
            G={playing_cards={A,K,A},hand={cards={K,A}},discard={cards={K}},jokers={cards={}},
               GAME={round_resets={hands=5,discards=2},probabilities={normal=1}}}''')
            lua.execute('endpoint=(function() '+source.read_text(encoding='utf-8')+' end)()')
            lua.execute('''endpoint.execute({},function(x)
              assert(#x.deck_multiset==2 and #x.visible_hand==1 and #x.visible_discard==0)
              for _,r in ipairs(x.deck_multiset) do assert(r.card.id==nil and r.card.index==nil and r.card.sort_id==nil) end
              old=x.deck_multiset
            end)
            G.playing_cards={K,A,A}
            endpoint.execute({},function(x)
              for i,r in ipairs(x.deck_multiset) do assert(r.card.key==old[i].card.key and r.count==old[i].count) end
            end)''')

if __name__=='__main__':unittest.main()
