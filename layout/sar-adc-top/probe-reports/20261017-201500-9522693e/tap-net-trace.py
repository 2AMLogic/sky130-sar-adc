import pya, os
ly = pya.Layout(); ly.read(os.environ["GDS"]); top=ly.top_cell(); top.flatten(True)
l2n = pya.LayoutToNetlist(pya.RecursiveShapeIterator(ly, top, []))
def L(a,b): return l2n.make_layer(ly.layer(a,b), "%d_%d"%(a,b))
li1=L(67,20);met1=L(68,20);met2=L(69,20);met3=L(70,20);met4=L(71,20);met5=L(72,20)
mcon=L(67,44);via=L(68,44);via2=L(69,44);via3=L(70,44);via4=L(71,44);licon=L(66,44);tap=L(65,44);poly=L(66,20)
txt={}
for k,(a,b) in {"li1":(67,5),"met1":(68,5),"met2":(69,5),"met3":(70,5),"met4":(71,5),"met5":(72,5)}.items():
    txt[k]=L(a,b)
for n,l in [("li1",li1),("met1",met1),("met2",met2),("met3",met3),("met4",met4),("met5",met5)]:
    l2n.connect(l)
l2n.connect(li1,mcon);l2n.connect(mcon,met1);l2n.connect(met1,via);l2n.connect(via,met2);l2n.connect(met2,via2);l2n.connect(via2,met3)
l2n.connect(met3,via3);l2n.connect(via3,met4);l2n.connect(met4,via4);l2n.connect(via4,met5)
l2n.extract_netlist()
# find net at tap li1
for pt in [(64.5,87.0),(90.8,87.0)]:
    p = pya.DPoint(*pt)
    n = l2n.probe_net(li1, p)
    print("PROBE",pt, n.expanded_name() if n else None)
    if n:
        cc = n.circuit()
        print(" circuit",cc.name, "cluster_id", n.cluster_id)
        names=set()
        for lname,lay in [("met1",met1),("met2",met2),("met3",met3),("met4",met4),("met5",met5),("li1",li1)]:
            r = l2n.shapes_of_net(n,lay,True)
            print(" ",lname,r.count(), r.bbox())
        for lname,lay in [("met1",met1),("met2",met2),("met3",met3),("met4",met4),("met5",met5),("li1",li1)]:
            pass
# labels: text on any label layer inside net's shapes
for pt in [(64.5,87.0),(90.8,87.0)]:
    n = l2n.probe_net(li1, pya.DPoint(*pt))
    found=[]
    for (a,b),lay in [((68,5),met1),((67,5),li1),((69,5),met2),((70,5),met3),((71,5),met4),((72,5),met5)]:
        reg = l2n.shapes_of_net(n,lay,True)
        li=ly.find_layer(a,b)
        if li is None: continue
        tr = pya.Region(top.begin_shapes_rec(li)) if False else None
        it=top.begin_shapes_rec(li)
        while not it.at_end():
            s=it.shape()
            if s.is_text():
                t=it.trans()*s.text
                pt2=pya.Point(t.trans.disp.x,t.trans.disp.y)
                if reg.interacting(pya.Region(pya.Box(pt2.x-1,pt2.y-1,pt2.x+1,pt2.y+1))).count()>0:
                    found.append((s.text_string,a))
            it.next()
    print("LABELS",pt,sorted(set(found)))
