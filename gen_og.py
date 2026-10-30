#!/usr/bin/env python3
"""Render the public share card from the same current catalog snapshot. No network."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

SITE = 'stacktracker'
ROOT = Path(__file__).resolve().parent
CARDS = {
 'model-radar': {'name':'Model Radar','host':'modelradar.kymatalabs.com','key':'models','kicker':'TRENDING ON HUGGING FACE · UPDATED DAILY','lines':[("What's ", 'surging', ' on Hugging'),('Face right now','','')],'description':'{count} trending AI models ranked by public Hugging Face signals — downloads, likes and freshness. Updated daily.'},
 'agent-velocity': {'name':'Agent Velocity','host':'agentvelocity.kymatalabs.com','key':'repos','kicker':'THE CODING-AGENT RACE · UPDATED DAILY','lines':[("Who's ",'shipping fastest',' in the'),('coding-agent race?','','')],'description':'{count} open-source coding agents ranked by public GitHub signals. Updated daily.'},
 'stacktracker': {'name':'StackTracker','host':'stacktracker.kymatalabs.com','key':'repos','kicker':'PUBLIC SOURCE SIGNALS · UPDATED DAILY','lines':[('The live ','momentum index',' for'),('AI infrastructure','','')],'description':'{count} projects ranked by public GitHub signals. Recomputed daily.'},
 'mcp-index': {'name':'The MCP Index','host':'mcp.kymatalabs.com','key':'servers','kicker':'OFFICIAL REGISTRY · UPDATED DAILY','lines':[('Every ','MCP server',', in one'),('living index','','')],'description':'{count} servers from the official registry. Searchable and freshness-tracked.'},
}

def font(name, size, weight=400):
    f = ImageFont.truetype(str(ROOT/'.build-assets'/'fonts'/name), size)
    axes = f.get_variation_axes()
    values = []
    for axis in axes:
        label = axis['name'].decode().lower()
        value = weight if 'weight' in label else (144 if 'optical' in label else axis['default'])
        values.append(max(axis['minimum'], min(axis['maximum'], value)))
    f.set_variation_by_axes(values)
    return f

def render(data, output):
    card=CARDS[SITE]
    entries=data.get(card['key'])
    if not isinstance(entries,list) or not entries:
        raise ValueError('A non-empty current public catalog snapshot is required')
    count=len(entries)
    ink='#191714'; accent='#c84808'; teal='#007f7b'; muted='#7d776b'
    img=Image.new('RGB',(1200,630),'#f5f2eb'); d=ImageDraw.Draw(img)
    d.arc((-60,187,1280,757),188,355,fill='#ebe6dd',width=1)
    d.arc((-240,250,1440,910),190,350,fill='#eee9e1',width=1)
    d.ellipse((81,78,119,116),outline=ink,width=2)
    d.ellipse((91,88,109,106),fill=accent)
    d.text((136,81),card['name'],font=font('fraunces.ttf',28,600),fill=ink,anchor='lt')
    kicker=card['kicker']; kfont=font('jetbrainsmono.ttf',15,500); x=80
    for char in '● '+kicker:
        d.text((x,180),char,font=kfont,fill=teal,anchor='lt'); x+=d.textlength(char,font=kfont)+2
    title_size=86
    while title_size>58:
        regular=font('fraunces.ttf',title_size); italic=font('fraunces-italic.ttf',title_size)
        if max(sum(d.textlength(v,font=italic if i==1 else regular) for i,v in enumerate(line)) for line in card['lines'])<=1040:break
        title_size-=1
    for row,line in enumerate(card['lines']):
        x=80; y=224+row*94
        for i,value in enumerate(line):
            f=italic if i==1 else regular;d.text((x,y),value,font=f,fill=accent if i==1 else ink,anchor='lt');x+=d.textlength(value,font=f)
    description=card['description'].format(count=f'{count:,}')
    mono=font('jetbrainsmono.ttf',22)
    lines=[];current=''
    for word in description.split():
        candidate=(current+' '+word).strip()
        if current and d.textlength(candidate,font=mono)>1040:lines.append(current);current=word
        else:current=candidate
    if current:lines.append(current)
    if len(lines)>3:raise ValueError('Card description exceeds its reserved layout')
    for i,line in enumerate(lines):d.text((80,421+i*31),line,font=mono,fill=ink,anchor='lt')
    footer=font('jetbrainsmono.ttf',16)
    d.text((80,540),'A Kymata Labs product',font=footer,fill=muted,anchor='lt')
    host_font=font('jetbrainsmono.ttf',16,600);host=card['host']
    d.text((1120-d.textlength(host,font=host_font),540),host,font=host_font,fill=accent,anchor='lt')
    meta=PngImagePlugin.PngInfo();meta.add_text('Title',card['name']);meta.add_text('Description',description);meta.add_text('CanonicalURL','https://'+host+'/');meta.add_text('Publisher','Kymata Labs LLC')
    output=Path(output);tmp=output.with_suffix('.tmp.png');img.save(tmp,pnginfo=meta);tmp.replace(output)
    return {'site':SITE,'count':count,'size':[1200,630],'canonical':'https://'+host+'/','description':description}

if __name__=='__main__':
    data=json.loads((ROOT/'data.json').read_text())
    receipt=render(data,ROOT/'og.png')
    render(data,ROOT/'og-20261030.png')
    print(json.dumps(receipt))
