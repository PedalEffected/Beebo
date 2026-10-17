#!/usr/bin/env python3
"""Generates droplets.ttl and manifest.ttl. Port order must match droplets.cc."""
URI = "https://github.com/PedalEffected/Beebo#Droplets"
# (kind, direction, symbol, name, extra)
ports = [
 ("AudioPort","Input","in_l","In L",{}),
 ("AudioPort","Input","in_r","In R",{}),
 ("AudioPort","Output","out_l","Out L",{}),
 ("AudioPort","Output","out_r","Out R",{}),
 ("CVPort","Input","seed_gate","Seed / clock",{"toggled":1}),
 ("CVPort","Input","freeze_gate","Freeze gate",{"toggled":1}),
 ("CVPort","Input","time_cv","Time CV",{}),
 ("CVPort","Input","size_cv","Size CV",{}),
 ("CVPort","Input","shape_cv","Shape CV",{}),
 ("CVPort","Input","pitch_cv","Pitch CV (1V/oct)",{}),
 ("CVPort","Input","density_cv","Density CV",{}),
 ("CVPort","Input","feedback_cv","Feedback CV",{}),
 ("CVPort","Input","dry_wet_cv","Dry/wet CV",{}),
 ("CVPort","Input","reverb_cv","Reverb CV",{}),
 ("ControlPort","Input","time","Time",{"def":0.5,"min":0,"max":1}),
 ("ControlPort","Input","size","Size",{"def":0.5,"min":0,"max":1}),
 ("ControlPort","Input","shape","Shape",{"def":0.5,"min":0,"max":1}),
 ("ControlPort","Input","density","Density",{"def":0.5,"min":0,"max":1}),
 ("ControlPort","Input","pitch","Pitch",{"def":0,"min":-24,"max":24,"unit":"semitone12TET"}),
 ("ControlPort","Input","time_amt","Time amount",{"def":0,"min":-1,"max":1}),
 ("ControlPort","Input","size_amt","Size amount",{"def":0,"min":-1,"max":1}),
 ("ControlPort","Input","shape_amt","Shape amount",{"def":0,"min":-1,"max":1}),
 ("ControlPort","Input","pitch_amt","Pitch amount",{"def":0,"min":-1,"max":1}),
 ("ControlPort","Input","feedback","Feedback",{"def":0.5,"min":0,"max":1}),
 ("ControlPort","Input","dry_wet","Dry/wet",{"def":0.5,"min":0,"max":1}),
 ("ControlPort","Input","reverb","Reverb",{"def":0.3,"min":0,"max":1}),
 ("ControlPort","Input","freeze","Freeze",{"def":0,"min":0,"max":1,"toggled":1}),
 ("ControlPort","Input","seed_button","Seed button",{"def":0,"min":0,"max":1,"toggled":1}),
 ("ControlPort","Input","seed_lock","Seed lock",{"def":1,"min":0,"max":1,"toggled":1}),
 ("ControlPort","Input","quality","Quality",{"def":3,"min":0,"max":3,"integer":1,
     "enum":[(0,"Dirty tape"),(1,"Clean tape"),(2,"Vintage digital"),(3,"Digital")]}),
 ("ControlPort","Input","mono","Mono input",{"def":0,"min":0,"max":1,"toggled":1}),
 ("ControlPort","Input","input_gain","Input gain (0 = auto)",{"def":0,"min":0,"max":1}),
 ("ControlPort","Input","synth","Synth mode",{"def":0,"min":0,"max":1,"toggled":1}),
 ("ControlPort","Input","gate_out","Right out = gate",{"def":0,"min":0,"max":1,"toggled":1}),
]
def fmt(v): return repr(float(v)) if not float(v).is_integer() else f"{float(v):.1f}"
out = []
for i,(kind,d,sym,name,x) in enumerate(ports):
    s = f"\t[\n\t\ta lv2:{kind} , lv2:{d}Port ;\n\t\tlv2:index {i} ;\n\t\tlv2:symbol \"{sym}\" ;\n\t\tlv2:name \"{name}\""
    if "def" in x: s += f" ;\n\t\tlv2:default {fmt(x['def'])} ;\n\t\tlv2:minimum {fmt(x['min'])} ;\n\t\tlv2:maximum {fmt(x['max'])}"
    if x.get("toggled"): s += " ;\n\t\tlv2:portProperty lv2:toggled"
    if x.get("integer"): s += " ;\n\t\tlv2:portProperty lv2:integer , lv2:enumeration"
    for v,l in x.get("enum",[]): s += f" ;\n\t\tlv2:scalePoint [ rdfs:label \"{l}\" ; rdf:value {v} ]"
    if "unit" in x: s += f" ;\n\t\tunits:unit units:{x['unit']}"
    out.append(s + "\n\t]")
hdr = ("@prefix doap: <http://usefulinc.com/ns/doap#> .\n@prefix lv2:  <http://lv2plug.in/ns/lv2core#> .\n"
       "@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
       "@prefix units: <http://lv2plug.in/ns/extensions/units#> .\n\n")
ttl = hdr + f"""<{URI}>
\ta lv2:Plugin , lv2:DelayPlugin ;
\tlv2:symbol "Droplets" ;
\tdoap:name "Droplets" ;
\tdoap:license <http://opensource.org/licenses/MIT> ;
\tlv2:minorVersion 1 ;
\tlv2:microVersion 0 ;
\tlv2:optionalFeature lv2:hardRTCapable ;
\tlv2:port
{' ,\n'.join(out)} ;
\trdfs:comment "Granular texture processor and delay, ported from the open-source Mutable Instruments Beads engine (MIT, Emilie Gillet)." .
"""
open("droplets.ttl","w").write(ttl)
open("manifest.ttl","w").write(hdr + f"<{URI}>\n\ta lv2:Plugin ;\n\tlv2:binary <droplets.so> ;\n\trdfs:seeAlso <droplets.ttl> .\n")
print(len(ports), "ports")
