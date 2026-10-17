import pya, os
ly = pya.Layout(); ly.read(os.environ["GDS"])
top = ly.top_cell()
print("top", top.name)
wells = [(63.825,85.850,70.565,90.620),(90.105,85.850,97.095,90.620)]
layers = [(64,20),(65,44),(66,44),(67,20),(67,44),(68,20),(93,44),(65,20)]
for w in wells:
    box = pya.Region(pya.DBox(*w).to_itype(ly.dbu))
    print("WELL", w)
    for l,d in layers:
        li = ly.find_layer(l,d)
        if li is None: print(" ",l,d,"absent"); continue
        r = pya.Region(top.begin_shapes_rec(li)) & box
        print(" ",l,d,"count",r.count(),"area_um2",round(r.area()*ly.dbu**2,3), "bboxes",[str(p.bbox()) for p in r.each()][:6])
