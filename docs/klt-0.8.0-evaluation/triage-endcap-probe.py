import json,sys
import klayout.db as db
gds,envp=sys.argv[1:3]
d=json.load(open(envp))
ly=db.Layout();ly.read(gds);top=ly.top_cell()
reg=lambda l,dt: db.Region(top.begin_shapes_rec(ly.layer(l,dt))).merged()
poly,diff=reg(66,20),reg(65,20)
seen=set()
for v in d['violations']:
    if v['rule']!='poly.endcap.diff.1': continue
    key=(v['source_cell'].split('$')[0],v['bbox']['right']-v['bbox']['left'])
    if key in seen: continue
    seen.add(key)
    b=v['bbox'];w=db.Box(b['left']-400,b['bottom']-400,b['right']+400,b['top']+400)
    print(key,'marker',b)
    print('  poly',[ (p.bbox().left,p.bbox().bottom,p.bbox().right,p.bbox().top) for p in (poly&db.Region(w)).each()][:4])
    print('  diff',[ (p.bbox().left,p.bbox().bottom,p.bbox().right,p.bbox().top) for p in (diff&db.Region(w)).each()][:4])
