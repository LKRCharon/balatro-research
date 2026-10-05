"""All 150 original Joker keys have explicit acquisition and activation policies.

Scores are initial policy priors, not measured card power. State conditions below and
whole-lineup forecasts decide actual purchases. Coverage does not imply optimal use.
"""
from collections import Counter
from copying import SPECS,COPY
import advisor as a

# Explicit priors for every original key; no unknown-card rejection or default score.
PRIORS={
'j_joker':36,'j_greedy_joker':45,'j_lusty_joker':45,'j_wrathful_joker':45,'j_gluttenous_joker':45,
'j_jolly':65,'j_zany':56,'j_mad':58,'j_crazy':54,'j_droll':60,'j_sly':60,'j_wily':55,'j_clever':56,'j_devious':55,'j_crafty':60,
'j_half':90,'j_stencil':88,'j_four_fingers':90,'j_mime':55,'j_credit_card':20,'j_ceremonial':85,'j_banner':66,'j_mystic_summit':65,
'j_marble':52,'j_loyalty_card':65,'j_8_ball':43,'j_misprint':58,'j_dusk':65,'j_raised_fist':68,'j_chaos':58,'j_fibonacci':90,
'j_steel_joker':45,'j_scary_face':65,'j_abstract':90,'j_delayed_grat':42,'j_hack':72,'j_pareidolia':35,'j_gros_michel':82,
'j_even_steven':65,'j_odd_todd':65,'j_scholar':80,'j_business':45,'j_supernova':91,'j_ride_the_bus':80,'j_space':65,'j_egg':50,
'j_burglar':96,'j_blackboard':80,'j_runner':85,'j_ice_cream':65,'j_dna':100,'j_splash':45,'j_blue_joker':85,'j_sixth_sense':48,
'j_constellation':89,'j_hiker':76,'j_faceless':38,'j_green_joker':93,'j_superposition':42,'j_todo_list':48,'j_cavendish':130,
'j_card_sharp':94,'j_red_card':60,'j_madness':94,'j_square':65,'j_seance':38,'j_riff_raff':83,'j_vampire':80,'j_shortcut':78,
'j_hologram':86,'j_vagabond':95,'j_baron':62,'j_cloud_9':60,'j_rocket':88,'j_obelisk':55,'j_midas_mask':40,'j_luchador':38,
'j_photograph':85,'j_gift':55,'j_turtle_bean':55,'j_erosion':35,'j_reserved_parking':40,'j_mail':65,'j_to_the_moon':75,
'j_hallucination':58,'j_fortune_teller':80,'j_juggler':60,'j_drunkard':55,'j_stone':40,'j_golden':68,'j_lucky_cat':55,
'j_baseball':83,'j_bull':90,'j_diet_cola':10,'j_trading':80,'j_flash':75,'j_popcorn':65,'j_trousers':94,'j_ancient':100,
'j_ramen':75,'j_walkie_talkie':78,'j_selzer':68,'j_castle':83,'j_smiley':76,'j_campfire':87,'j_ticket':40,'j_mr_bones':64,
'j_acrobat':78,'j_sock_and_buskin':72,'j_swashbuckler':55,'j_troubadour':45,'j_certificate':85,'j_smeared':65,'j_throwback':40,
'j_hanging_chad':86,'j_rough_gem':42,'j_bloodstone':83,'j_arrowhead':88,'j_onyx_agate':82,'j_glass':45,'j_ring_master':38,
'j_flower_pot':48,'j_blueprint':165,'j_wee':80,'j_merry_andy':68,'j_oops':45,'j_idol':70,'j_seeing_double':83,'j_matador':35,
'j_hit_the_road':64,'j_duo':88,'j_trio':80,'j_family':55,'j_order':78,'j_tribe':78,'j_stuntman':95,'j_invisible':92,
'j_brainstorm':160,'j_satellite':50,'j_shoot_the_moon':76,'j_drivers_license':50,'j_cartomancer':82,'j_astronomer':65,
'j_burnt':100,'j_bootstraps':80,'j_caino':120,'j_triboulet':180,'j_yorick':115,'j_chicot':110,'j_perkeo':155}
assert set(PRIORS)==set(SPECS),(set(SPECS)-set(PRIORS),set(PRIORS)-set(SPECS))

PHASE_GROUPS={
'copy':{'j_blueprint','j_brainstorm'},
'blind_entry':{'j_burglar','j_certificate','j_marble','j_cartomancer','j_riff_raff','j_ceremonial','j_madness'},
'first_play':{'j_dna','j_sixth_sense'},
'discard':{'j_burnt','j_trading','j_mail','j_castle','j_hit_the_road','j_yorick','j_faceless'},
'shop_exit':{'j_perkeo'},
'sell':{'j_luchador','j_diet_cola','j_invisible'},
'held_cards':{'j_baron','j_mime','j_shoot_the_moon','j_raised_fist','j_reserved_parking'},
'economy':{'j_egg','j_gift','j_golden','j_rocket','j_satellite','j_cloud_9','j_to_the_moon','j_delayed_grat'},
'deck_build':{'j_steel_joker','j_stone','j_erosion','j_drivers_license','j_hologram','j_glass','j_lucky_cat','j_caino'},
'passive':{'j_four_fingers','j_shortcut','j_smeared','j_pareidolia','j_splash','j_oops','j_juggler','j_troubadour','j_stuntman',
           'j_drunkard','j_merry_andy','j_turtle_bean','j_ring_master','j_astronomer','j_credit_card','j_chicot','j_mr_bones','j_chaos'},
}

def phase(key):return next((n for n,keys in PHASE_GROUPS.items() if key in keys),'scoring')

def value(c,s):
    k=c['key'];v=PRIORS[k];ks=a.keys(s);ante=s['ante_num'];deck=s.get('_belief',{}).get('deck',[])
    mods=Counter(a.mod(c).get('enhancement') for c in deck);ranks=Counter(a.rank(c) for c in deck)
    if k in COPY:
        compatible=[j for j in s['jokers']['cards'] if SPECS[j['key']]['blueprint_compat'] and j['key'] not in COPY]
        v+=20 if compatible else -70
    if k=='j_dna':v+=35*bool(ks&{'j_hologram','j_blueprint','j_brainstorm'})-20*(ante>=6)
    if k=='j_hologram':v+=45*bool(ks&{'j_dna','j_certificate','j_marble'})
    if k=='j_mime':v+=min(90,mods['STEEL']*8)+45*bool(ks&{'j_baron','j_shoot_the_moon'})
    if k=='j_baron':v+=min(75,max(0,ranks[13]-4)*10)+35*('j_mime' in ks)
    if k=='j_hack':v+=25*bool(ks&{'j_wee','j_fibonacci','j_hiker'})
    if k=='j_wee':v+=30*bool(ks&{'j_hack','j_hanging_chad','j_dna'})-25*(ante>=5)
    if k=='j_pareidolia':v+=50*bool(ks&{'j_photograph','j_sock_and_buskin','j_scary_face','j_smiley','j_midas_mask'})
    if k=='j_steel_joker':v+=min(100,mods['STEEL']*12)-20*(mods['STEEL']==0)
    if k=='j_stone':v+=min(90,mods['STONE']*15)+35*('j_marble' in ks)
    if k=='j_erosion':v+=min(100,max(0,52-len(deck))*8)+30*('j_trading' in ks)
    if k=='j_drivers_license':v+=90*(sum(n for e,n in mods.items() if e)>=16)
    if k=='j_lucky_cat':v+=min(80,mods['LUCKY']*8)+30*bool(ks&{'j_oops','j_hanging_chad'})
    if k=='j_glass':v+=min(80,mods['GLASS']*15)
    if k=='j_midas_mask':v+=70*('j_vampire' in ks)+30*('j_ticket' in ks)
    if k=='j_vampire':v+=45*('j_midas_mask' in ks)+min(40,sum(n for e,n in mods.items() if e)*3)
    if k=='j_ticket':v+=min(65,mods['GOLD']*10)+30*('j_midas_mask' in ks)
    if k=='j_oops':v+=55*bool(ks&{'j_bloodstone','j_lucky_cat','j_space'})
    if k=='j_seance':v+=45*('j_four_fingers' in ks)
    if k=='j_superposition':v+=35*bool(ks&{'j_shortcut','j_four_fingers','j_runner'})
    if k=='j_baseball':v+=16*sum(SPECS[j['key']]['rarity']==2 for j in s['jokers']['cards'])
    if k=='j_obelisk':
        levels=sorted((h.get('played',0) for h in s['hands'].values()),reverse=True)
        v+=70*(levels[0]>=12 and levels[0]-levels[1]>=7)
    if k=='j_madness':
        exposed=[j for j in s['jokers']['cards'] if not a.mod(j).get('eternal') and j is not c]
        v-=min(120,30*len(exposed));v+=25*sum(a.mod(j).get('eternal',False) for j in s['jokers']['cards'])
    if k=='j_riff_raff':v-=35*(len(s['jokers']['cards'])>=4)+35*(ante>=4)
    if k=='j_marble' and not ks&{'j_stone','j_hologram'}:v-=30
    if k=='j_ceremonial':v+=35*bool(ks&{'j_egg','j_gift','j_riff_raff'})-35*(ante>=5)
    if k in ('j_egg','j_gift','j_swashbuckler'):v+=30*bool(ks&{'j_ceremonial','j_swashbuckler','j_gift','j_egg'}-{k})
    if k=='j_trading':v+=35*bool(ks&{'j_caino','j_erosion'})
    if k=='j_hit_the_road':v+=25*bool(ks&{'j_merry_andy','j_drunkard'})
    if k=='j_vagabond':v+=25*(s['money']<=4)-40*(s['money']>=25)
    if k=='j_matador':v+=45*(s['blinds']['boss']['name'] in ('The Psychic','The Eye','The Mouth','The Flint'))
    if k=='j_invisible':v-=70*a.mod(c).get('eternal',False);v-=45*(ante>=7)
    if k=='j_luchador':v-=70*a.mod(c).get('eternal',False);v+=45*(ante>=6)
    if k=='j_diet_cola':v-=70*a.mod(c).get('eternal',False)
    if k=='j_throwback':v+=30*max(0,a.current_number(c,1)-1)
    if k=='j_stencil':v+=25*(len(s['jokers']['cards'])<=2)
    return v

def card_value(c,s):
    ks=a.keys(s);m=a.mod(c);r=a.rank(c)
    v=r+{'STEEL':45,'GLASS':38,'MULT':22,'BONUS':18,'LUCKY':25,'GOLD':15,'WILD':8,'STONE':8}.get(m.get('enhancement'),0)
    v+={'BLUE':80,'RED':55,'PURPLE':45,'GOLD':22}.get(m.get('seal'),0)
    v+={'POLYCHROME':70,'HOLO':40,'FOIL':35}.get(m.get('edition'),0)+c.get('permanent_bonus',0)*.8
    v+=70*(r==13 and 'j_baron' in ks)+60*(r in (12,13) and 'j_triboulet' in ks)+50*(r==2 and 'j_wee' in ks)
    return v
