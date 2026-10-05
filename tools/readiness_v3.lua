-- Original transport barrier: waits for normal UI locks; never bypasses legality.
if os.getenv('BALATRO_CLI') ~= '1' then return end
assert(love.filesystem.getIdentity():match('^Balatro%-Lab%-Headless%-'))
local pending = {}
local stats = {pre_waits=0, post_waits=0, timeouts=0}
local function transient()
  if not G or not G.GAME or not G.CONTROLLER then return true end
  return G.CONTROLLER.locked or (G.GAME.STOP_USE or 0) > 0
    or (G.play and G.play.cards and #G.play.cards > 0)
end
local function wait_ready(run, fail, phase)
  if not transient() then run(); return end
  stats[phase .. '_waits'] = stats[phase .. '_waits'] + 1
  pending[#pending+1] = {run=run, fail=fail, deadline=love.timer.getTime()+15}
end
table.insert(BB_CORE.after_load, function()
  for _, name in ipairs({'cash_out','buy','pack','use'}) do
    local endpoint = assert(BB_DISPATCHER.endpoints[name])
    local original = endpoint.execute
    endpoint.execute = function(args, reply)
      local invoked, replied = false, false
      local function once(value)
        if not replied then replied=true; reply(value) end
      end
      local function timeout(phase)
        stats.timeouts = stats.timeouts + 1
        once({message='Readiness timeout ('..phase..'); action_started='..tostring(invoked)..'; do not retry',
          name=BB_ERROR_NAMES.INTERNAL_ERROR})
      end
      local initial_state = G.STATE
      local function execute()
        if G.STATE ~= initial_state then
          once({message='State changed while awaiting readiness; action not executed', name=BB_ERROR_NAMES.INVALID_STATE})
          return
        end
        if invoked then return end
        invoked=true
        original(args, function(result)
          if result.message then once(result); return end
          wait_ready(function() once(BB_GAMESTATE.get_gamestate()) end,
            function() timeout('completion') end, 'post')
        end)
      end
      if name == 'use' or name == 'pack' or name == 'buy' then
        wait_ready(execute, function() timeout('before execution') end, 'pre')
      else execute() end
    end
  end
  local update = love.update
  love.update = function(dt)
    update(dt)
    local old = pending; pending = {}
    for _, item in ipairs(old) do
      if not transient() then item.run()
      elseif love.timer.getTime() >= item.deadline then item.fail()
      else pending[#pending+1] = item end
    end
  end
  assert(BB_DISPATCHER.register({name='lab_readiness',description='Read-only transport readiness diagnostics',schema={},
    execute=function(_,reply)
      reply({ready=not transient(),locked=not not G.CONTROLLER.locked,stop_use=G.GAME.STOP_USE or 0,
        play_cards=G.play and #G.play.cards or 0,pre_waits=stats.pre_waits,post_waits=stats.post_waits,timeouts=stats.timeouts})
    end}))
end)
