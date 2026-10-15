"""Conservative mass-only filter-cake washing balance. No equilibrium/heat claims."""
import math

def wash_balance(*, dry_insolubles, retained_water, retained_naoh, retained_na2co3, filtrate_water, filtrate_naoh, filtrate_na2co3, wash_water, target_moisture=0.25, displacement_factor=1.0):
    values=locals()
    if any(not math.isfinite(v) for v in values.values()):
        raise ValueError('All inputs must be finite')
    if any(v<0 for k,v in values.items() if k!='target_moisture') or not 0<target_moisture<1:
        raise ValueError('Negative mass/kinetic factor or invalid moisture')
    if retained_water<=0 and wash_water>0: raise ValueError('Wet-cake water must be positive for wash model')
    efficiency=0.0 if wash_water==0 or retained_water==0 else -math.expm1(-displacement_factor*wash_water/retained_water)
    new_naoh=retained_naoh*(1-efficiency)
    new_carbonate=retained_na2co3*(1-efficiency)
    if wash_water==0:
        new_water=retained_water  # preserve exact unwashed native baseline
    else:
        new_water=target_moisture/(1-target_moisture)*(dry_insolubles+new_naoh+new_carbonate)
        if new_water>retained_water+wash_water+1e-10:
            raise ValueError('Insufficient water to meet washed cake target')
    out={
      'efficiency_ASSUMED':efficiency,
      'cake':{'Water':new_water,'NaOH':new_naoh,'Na2CO3':new_carbonate},
      'filtrate':{'Water':filtrate_water+retained_water+wash_water-new_water,
                  'NaOH':filtrate_naoh+retained_naoh-new_naoh,
                  'Na2CO3':filtrate_na2co3+retained_na2co3-new_carbonate},
      'dry_insolubles':dry_insolubles,
      'wash_water':wash_water,
    }
    for ID in ('Water','NaOH','Na2CO3'):
        initial=(retained_water+filtrate_water+wash_water if ID=='Water' else
            retained_naoh+filtrate_naoh if ID=='NaOH' else retained_na2co3+filtrate_na2co3)
        final=out['cake'][ID]+out['filtrate'][ID]
        if abs(final-initial)>1e-9*max(1.0,initial): raise ArithmeticError(f'{ID} balance failure')
        if out['filtrate'][ID]<-1e-12: raise ArithmeticError('Negative filtrate mass')
    out['cake_moisture']=new_water/(dry_insolubles+sum(out['cake'].values())) if (dry_insolubles+sum(out['cake'].values())) else 0
    return out
