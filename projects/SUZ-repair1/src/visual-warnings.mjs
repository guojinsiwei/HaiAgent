// Conditional, task-local visual hints. No action is prohibited by this registry.
const text=x=>typeof x==='string'&&x.trim().length>0;
export function validBox(box) {
  return Array.isArray(box)&&box.length===4&&box.every(x=>Number.isFinite(x)&&x>=0&&x<=1)&&
    box[2]>box[0]&&box[3]>box[1]&&(box[2]-box[0])*(box[3]-box[1])<=0.25;
}
export class VisualWarnings {
  constructor(state=null) {this.state=state??{next:1,items:[]};}
  observe(frame) {
    for(const item of this.state.items) {
      if(['cleared','expired'].includes(item.status))continue;
      if(frame.step>=item.expires_step)item.status='expired';
      else if(frame.sha256!==item.anchor_sha256)item.status='needs_revalidation';
      // Returning to an old screenshot never resurrects a stale condition automatically.
    }
  }
  add(value,frame,evidence,memoryId) {
    if(value.frame_id!==frame.id||!validBox(value.box)||!text(value.target)||!text(value.condition)||
       !text(value.diagnosis)||!['disabled','occluded','wrong_gesture','loading','unknown'].includes(value.cause)||
       !Number.isFinite(value.confidence)||value.confidence<0||value.confidence>1)
      throw new Error('invalid current-screen visual warning');
    const ids=value.evidence_ids;
    if(!Array.isArray(ids)||new Set(ids).size<2||ids.length>3||ids.some(id=>!evidence[id])||
       !ids.some(id=>evidence[id].frame_ids.at(-1)===frame.id))throw new Error('warning needs 2-3 executed transitions including current screen');
    const points=ids.flatMap(id=>evidence[id].action.points??[]);
    if(!points.some(p=>p.x>=value.box[0]&&p.x<=value.box[2]&&p.y>=value.box[1]&&p.y<=value.box[3]))
      throw new Error('warning must localize an observed click');
    const duplicate=this.state.items.find(x=>x.status==='active'&&x.anchor_sha256===frame.sha256&&
      x.target===value.target&&x.condition===value.condition);
    if(duplicate)return duplicate;
    const item={id:`V${this.state.next++}`,frame_id:frame.id,anchor_sha256:frame.sha256,
      created_step:frame.step,expires_step:frame.step+3,status:'active',box:[...value.box],
      target:value.target,condition:value.condition,diagnosis:value.diagnosis,cause:value.cause,
      confidence:value.confidence,evidence_ids:[...ids],memory_id:memoryId,
      style:value.confidence>=0.7&&['disabled','occluded','wrong_gesture'].includes(value.cause)?'red_cross':'amber_box',
      semantics:'attributed conditional warning; not an execution ban or verified failure'};
    this.state.items.push(item);this.state.items=this.state.items.slice(-32);
    return item;
  }
  update(value,frame) {
    const item=this.state.items.find(x=>x.id===value.id);
    if(!item||['cleared','expired'].includes(item.status)||!text(value.reason)||value.frame_id!==frame.id)
      throw new Error('warning update needs a live ID and current-frame reason');
    if(value.decision==='clear') {item.status='cleared';item.clear_reason=value.reason;return item;}
    if(value.decision!=='revalidate'||!validBox(value.box)||!text(value.condition))
      throw new Error('warning revalidation needs localized current condition');
    item.box=[...value.box];item.condition=value.condition;item.frame_id=frame.id;
    item.anchor_sha256=frame.sha256;item.status='active';item.revalidation_reason=value.reason;
    // Original expiry remains: revalidation cannot extend a negative memory forever.
    return item;
  }
  view() {return structuredClone(this.state.items.filter(x=>!['expired','cleared'].includes(x.status)).slice(-6));}
}
