"""Readiness regressions; install optional test dependency lupa to run Lua tests."""
import json
from pathlib import Path
import tempfile
import unittest
from readiness_patch import install
try:
    from lupa import LuaRuntime
except ImportError:
    LuaRuntime = None


@unittest.skipIf(LuaRuntime is None, 'Lua behavioral tests require lupa')
class BarrierTests(unittest.TestCase):
    helper_name = 'readiness_v2.lua'
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute('''
        os.getenv=function() return '1' end
        clock=0; executed=0; replies=0; rejected=false
        love={filesystem={getIdentity=function() return 'Balatro-Lab-Headless-test' end},
          timer={getTime=function() return clock end},update=function() end}
        G={STATE=1, GAME={STOP_USE=0},CONTROLLER={locked=false},play={cards={}}}
        BB_CORE={after_load={}}
        BB_ERROR_NAMES={INTERNAL_ERROR='internal',INVALID_STATE='state'}
        BB_GAMESTATE={get_gamestate=function() return {state=G.STATE,fresh=true} end}
        BB_DISPATCHER={endpoints={},register=function(e) BB_DISPATCHER.endpoints[e.name]=e;return true end}
        for _,n in ipairs({'use','pack','cash_out','buy'}) do
          BB_DISPATCHER.endpoints[n]={execute=function(args,reply)
            executed=executed+1
            if rejected then reply({message='genuine legality rejection'}); return end
            if args.lock_after then G.GAME.STOP_USE=2 end
            reply({state=1})
          end}
        end
        reply=function(r) replies=replies+1;last=r end
        ''')
        self.lua.execute(Path(__file__).with_name(self.helper_name).read_text(encoding='utf-8-sig'))
        self.lua.execute('for _,f in ipairs(BB_CORE.after_load) do f() end')

    def test_pre_wait_does_not_execute_twice(self):
        self.lua.execute("G.GAME.STOP_USE=1;BB_DISPATCHER.endpoints.use.execute({},reply)")
        self.assertEqual(self.lua.globals().executed,0)
        self.lua.execute('G.GAME.STOP_USE=0;love.update(0);love.update(0)')
        self.assertEqual(self.lua.globals().executed,1)
        self.assertEqual(self.lua.globals().replies,1)

    def test_cashout_waits_and_refreshes_observation(self):
        self.lua.execute('BB_DISPATCHER.endpoints.cash_out.execute({lock_after=true},reply)')
        self.assertEqual(self.lua.globals().replies,0)
        self.lua.execute('G.STATE=2;G.GAME.STOP_USE=0;love.update(0)')
        self.assertEqual(self.lua.globals().last['state'],2)

    def test_legality_rejection_is_not_retried(self):
        self.lua.execute('rejected=true;BB_DISPATCHER.endpoints.use.execute({},reply);love.update(0)')
        self.assertEqual(self.lua.globals().executed,1)
        self.assertEqual(self.lua.globals().last['message'],'genuine legality rejection')

    def test_timeout_no_pre_mutation(self):
        self.lua.execute('G.CONTROLLER.locked=true;BB_DISPATCHER.endpoints.use.execute({},reply);clock=16;love.update(0)')
        self.assertEqual(self.lua.globals().executed,0)
        self.assertIn('action_started=false',self.lua.globals().last['message'])

    def test_post_timeout_marks_ambiguity(self):
        self.lua.execute('BB_DISPATCHER.endpoints.buy.execute({lock_after=true},reply);clock=16;love.update(0);love.update(0)')
        self.assertEqual(self.lua.globals().executed,1)
        self.assertEqual(self.lua.globals().replies,1)
        self.assertIn('action_started=true',self.lua.globals().last['message'])

    def test_state_change_aborts_before_execute(self):
        self.lua.execute('G.CONTROLLER.locked=true;BB_DISPATCHER.endpoints.pack.execute({},reply);G.STATE=2;G.CONTROLLER.locked=false;love.update(0)')
        self.assertEqual(self.lua.globals().executed,0)
        self.assertEqual(self.lua.globals().last['name'],'state')

    def test_play_area_is_a_transient_guard(self):
        self.lua.execute('G.play.cards={1};BB_DISPATCHER.endpoints.use.execute({},reply);love.update(0)')
        self.assertEqual(self.lua.globals().executed,0)
        self.lua.execute('G.play.cards={};love.update(0)')
        self.assertEqual(self.lua.globals().executed,1)


class BarrierV3Tests(BarrierTests):
    helper_name = 'readiness_v3.lua'

    def test_buy_waits_before_game_legality_check(self):
        self.lua.execute('G.GAME.STOP_USE=1;BB_DISPATCHER.endpoints.buy.execute({use=true},reply)')
        self.assertEqual(self.lua.globals().executed,0)
        self.lua.execute('G.GAME.STOP_USE=0;love.update(0);love.update(0)')
        self.assertEqual(self.lua.globals().executed,1)
        self.assertEqual(self.lua.globals().replies,1)


class InstallerTests(unittest.TestCase):
    def test_reject_existing_launch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'launcher.json').write_text('{}')
            path=root/'instance.json'
            path.write_text(json.dumps({'root':d,'checkout':str(root/'checkout'),'identity':'Balatro-Lab-Headless-test'}))
            with self.assertRaisesRegex(ValueError,'never-launched'):install(path)


if __name__=='__main__':unittest.main()
