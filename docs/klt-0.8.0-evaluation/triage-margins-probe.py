import json,sys,collections
import klayout.db as db
gds,envp=sys.argv[1:3]
d=json.load(open(envp))
ly=db.Layout();ly.read(gds)
top=ly.top_cell()
L=lambda l,dt:ly.layer(l,dt)
def reg(l,dt): return db.Region(top.begin_shapes_rec(L(l,dt))).merged()
R={n:reg(*k) for n,k in dict(m1=(68,20),m2=(69,20),m3=(70,20),via1=(68,44),via2=(69,44),via3=(70,44),poly=(66,20),diff=(65,20),capm=(89,44)).items()}
def margins(metal,via):
    out=collections.Counter()
    for v in via.each():
        b=v.bbox()
        sides=[]
        for nm,(box) in dict(L=db.Box(b.left-1000,b.bottom,b.left,b.top),R=db.Box(b.right,b.bottom,b.right+1000,b.top),B=db.Box(b.left,b.bottom-1000,b.right,b.bottom),T=db.Box(b.left,b.top,b.right,b.top+1000)).items():
            reg_=db.Region(box)
            # distance covered by metal contiguous from via edge
            hit=(metal&reg_)
            if hit.is_empty(): sides.append(0);continue
            bb=hit.bbox()
            sides.append({'L':b.left-bb.left,'R':bb.right-b.right,'B':b.bottom-bb.bottom,'T':bb.top-b.top}[nm])
        # clamp
        out[tuple(sides)]+=1
    return out
def vias_at(via,markers):
    sel=db.Region()
    for m in markers: sel+=db.Region(db.Box(*m))
    return via.interacting(sel)
fam=collections.defaultdict(list)
for v in d['violations']:
    b=v['bbox'];fam[v['rule']].append((b['left'],b['bottom'],b['right'],b['top']))
for rule,metal,via in [('met1.enclosing_adjacent.via.1','m1','via1'),('met2.enclosing_adjacent.via.1','m2','via1'),('met2.enclosing_adjacent.via2.1','m2','via2')]:
    vs=vias_at(R[via],fam[rule])
    print(rule,'n_vias',vs.count(),'(L,R,B,T) margins nm:')
    for k,c in margins(R[metal],vs).most_common(6): print('  ',k,c)
vs=vias_at(R['via3'],fam['via3.width.1'])
print('via3 sizes',collections.Counter((v.bbox().width(),v.bbox().height()) for v in vs.each()),'on capm',(vs&R['capm']).count() if not R['capm'].is_empty() else 'no capm layer')
print('all via3 sizes',collections.Counter((v.bbox().width(),v.bbox().height()) for v in R['via3'].each()).most_common(5))
# endcap: gate = poly&diff ; endcap measured along poly past diff
mk=fam['poly.endcap.diff.1']
c=collections.Counter()
for m in mk:
    box=db.Box(*m)
    c[(box.width(),box.height(),'diff_in_marker', not (R['diff']&db.Region(box)).is_empty(),'poly_in_marker',not (R['poly']&db.Region(box)).is_empty())]+=1
print('endcap markers',c.most_common(8))
