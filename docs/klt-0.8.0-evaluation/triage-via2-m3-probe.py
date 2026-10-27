import json,sys,collections
import klayout.db as db
gds,envp=sys.argv[1:3]
d=json.load(open(envp))
ly=db.Layout();ly.read(gds);top=ly.top_cell()
reg=lambda l,dt: db.Region(top.begin_shapes_rec(ly.layer(l,dt))).merged()
m2,m3,via2,poly,diff,tap=reg(69,20),reg(70,20),reg(69,44),reg(66,20),reg(65,20),reg(65,44)
mk=[v for v in d['violations'] if v['rule']=='met2.enclosing_adjacent.via2.1']
sel=db.Region()
for v in mk:
    b=v['bbox'];sel+=db.Region(db.Box(b['left'],b['bottom'],b['right'],b['top']))
vs=via2.interacting(sel)
def encl(metal,via):
    c=collections.Counter()
    for v in via.each():
        b=v.bbox();s=[]
        for nm,box in dict(L=db.Box(b.left-300,b.bottom,b.left,b.top),R=db.Box(b.right,b.bottom,b.right+300,b.top),B=db.Box(b.left,b.bottom-300,b.right,b.bottom),T=db.Box(b.left,b.top,b.right,b.top+300)).items():
            h=metal&db.Region(box)
            if h.is_empty(): s.append(0);continue
            bb=h.bbox();s.append({'L':b.left-bb.left,'R':bb.right-b.right,'B':b.bottom-bb.bottom,'T':bb.top-b.top}[nm])
        # adjacent pair >=85 ?
        L,R,B,T=s
        ok=any(x>=85 and y>=85 for x,y in [(L,B),(L,T),(R,B),(R,T)])
        c[ok]+=1
    return c
print('via2 count',vs.count(),'m2 adj-pair ok?',encl(m2,vs),'m3 adj-pair ok?',encl(m3,vs))
# poly endcap markers
mk=[v for v in d['violations'] if v['rule']=='poly.endcap.diff.1']
c=collections.Counter()
for v in mk:
    b=v['bbox'];box=db.Box(b['left'],b['bottom'],b['right'],b['top'])
    grow=db.Region(box).sized(10)
    c[(v['source_cell'].split('$')[0],box.width(),box.height(),'touch_poly',not (poly&grow).is_empty(),'touch_diff',not (diff&grow).is_empty())]+=1
for k,n in c.most_common(12): print(n,k)
