"""Render fictional source records into labeled demo images; never invent evidence."""
import hashlib,json,textwrap
from pathlib import Path
from datetime import datetime,timezone
from PIL import Image,ImageDraw,ImageFont
from app.config import settings
from app.evidence_tools import context,EvidenceTools

FOLDER=Path(settings.investigation_archive)/'images'
FONT='/System/Library/Fonts/Supplemental/Arial.ttf'
BOLD='/System/Library/Fonts/Supplemental/Arial Bold.ttf'
def font(n,bold=False):return ImageFont.truetype(BOLD if bold else FONT,n)
def lines(draw,text,x,y,width=73,size=26,color='#203b46'):
 for line in textwrap.wrap(text,width=width,break_long_words=False) or ['']:
  draw.text((x,y),line,font=font(size),fill=color);y+=size+13
 return y

def build():
 FOLDER.mkdir(parents=True,exist_ok=True);records=[]
 specs=[('CASE-0088C625','CHAT-FLAG-CASE-0088C625','Apple desk conversation'),('CASE-52074E40','E-000114','NVIDIA trade instruction')]
 for cid,eid,title in specs:
  ctx=context(cid);source=next(r for r in EvidenceTools('render-only',cid,None).records(['communication','mandate']) if r['evidence_id']==eid and r['status']=='available')
  metadata=json.loads(source['metadata_json']);im=Image.new('RGB',(1280,1100),'#f2f6f7');draw=ImageDraw.Draw(im)
  draw.rectangle((0,0,1280,120),fill='#173c43');draw.text((48,28),'SUMMIT | '+title,font=font(34,True),fill='white')
  draw.text((48,82),'SYNTHETIC DEMO · Rendered from an existing fictional source',font=font(22),fill='#c9e9e5')
  draw.text((48,151),cid+'  |  '+eid,font=font(25,True),fill='#176e68');y=212
  if metadata.get('messages'):
   for m in metadata['messages']:
    height=(len(textwrap.wrap(m['text'],width=69))+1)*40+70
    draw.rounded_rectangle((42,y,1238,y+height),radius=16,fill='white',outline='#d9e3e5',width=2)
    draw.text((68,y+20),m['sender']+' · '+m['role'],font=font(27,True),fill='#173c43')
    draw.text((68,y+58),m['at'],font=font(20),fill='#61747b')
    lines(draw,m['text'],68,y+96,width=69,size=27);y+=height+22
  else:
   draw.rounded_rectangle((42,y,1238,y+350),radius=16,fill='white',outline='#d9e3e5',width=2)
   draw.text((68,y+25),'SOURCE DOCUMENT EXCERPT',font=font(23,True),fill='#176e68')
   lines(draw,source['content'],68,y+90,width=65,size=29);y+=390
   y=lines(draw,'Linked case order: '+', '.join(ctx['order_ids']),48,y,width=82,size=24)
   y=lines(draw,'Signature status is a recorded field, not independent authentication of a document or signer.',48,y+25,width=82,size=24)
  footer=max(y+15,945)
  draw.line((48,footer,1232,footer),fill='#bacdd2',width=2)
  lines(draw,'DERIVED RENDERING: same evidence as the source record, not independent corroboration. Verify text, timestamps and authority against the original record.',48,footer+20,width=97,size=21,color='#52676b')
  im=im.crop((0,0,1280,min(1100,footer+135)))
  image_id='IMG-'+cid.removeprefix('CASE-');path=FOLDER/(image_id+'.png');im.save(path)
  records.append({'image_id':image_id,'case_id':cid,'source_evidence_id':eid,'title':title,'filename':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'data_cutoff':ctx['cutoff'],'rendered_at':datetime.now(timezone.utc).isoformat(),'origin':'synthetic_source_rendering','limitation':'Fictional source rendered into an image. The image and paired text are the same evidence, not independent corroboration. Document authenticity is unverified.'})
  print(image_id,path)
 (FOLDER.parent/'images.json').write_text(json.dumps(records,indent=2))
if __name__=='__main__':build()
