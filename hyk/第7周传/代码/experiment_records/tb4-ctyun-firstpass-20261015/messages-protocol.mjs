// Validate a buffered Messages response before any fragment reaches DSH.
// Never repair or invent model content, tool arguments, usage, or stop reasons.
export function decodeSSE(text) {
  const events=[];
  for(const frame of text.replace(/\r\n/g,'\n').split(/\n\n/)) {
    const data=frame.split('\n').filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trimStart());
    if(!data.length)continue;
    try {events.push(JSON.parse(data.join('\n')));}
    catch {return {events,malformed:true};}
  }
  return {events,malformed:false};
}

const object=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
export function validateMessages(text) {
  const {events,malformed}=decodeSSE(text);
  const bad=reason=>({complete:false,reason});
  if(malformed)return bad('invalid_sse_json');
  let started=false,stopped=false,reason=null;
  const blocks=new Map(),toolIds=new Set();
  for(const e of events) {
    if(!object(e))return bad('invalid_event');
    if(e.type==='ping')continue;
    if(stopped)return bad('event_after_message_stop');
    if(e.type==='error')return bad('provider_error');
    if(e.type==='message_start') {
      if(started||!object(e.message))return bad('invalid_message_start');
      started=true;continue;
    }
    if(!started)return bad('missing_message_start');
    if(e.type==='content_block_start') {
      const b=e.content_block;
      if(reason!==null||!Number.isSafeInteger(e.index)||e.index<0||blocks.has(e.index)||!object(b))return bad('invalid_block_start');
      if(!['text','thinking','tool_use'].includes(b.type))return bad('unsupported_block');
      if(b.type==='text'&&typeof b.text!=='string')return bad('invalid_text_block');
      if(b.type==='thinking'&&typeof b.thinking!=='string')return bad('invalid_thinking_block');
      if(b.type==='tool_use') {
        if(typeof b.id!=='string'||!b.id||toolIds.has(b.id)||typeof b.name!=='string'||!b.name||!object(b.input))return bad('invalid_tool_identity');
        toolIds.add(b.id);
      }
      blocks.set(e.index,{type:b.type,closed:false,json:'',input:b.input});
    } else if(e.type==='content_block_delta'||e.type==='content_block_stop') {
      const b=blocks.get(e.index);
      if(!b||b.closed||reason!==null)return bad('block_not_open');
      if(e.type==='content_block_stop') {
        b.closed=true;
        if(b.type==='tool_use'&&b.json) {
          try {if(!object(JSON.parse(b.json)))return bad('invalid_tool_json');}
          catch{return bad('invalid_tool_json');}
        }
      } else {
        const d=e.delta;
        const allowed={text:['text_delta'],thinking:['thinking_delta','signature_delta'],tool_use:['input_json_delta']};
        if(!object(d)||!allowed[b.type].includes(d.type))return bad('invalid_block_delta');
        const key={text_delta:'text',thinking_delta:'thinking',signature_delta:'signature',input_json_delta:'partial_json'}[d.type];
        if(typeof d[key]!=='string')return bad('invalid_delta_payload');
        if(b.type==='tool_use')b.json+=d.partial_json;
      }
    } else if(e.type==='message_delta') {
      if(!object(e.delta))return bad('invalid_message_delta');
      if(e.delta.stop_reason!=null) {
        if(reason!==null||![...blocks.values()].every(b=>b.closed))return bad('unclosed_blocks');
        if(!['end_turn','stop_sequence','tool_use','max_tokens'].includes(e.delta.stop_reason))return bad('unsupported_stop_reason');
        reason=e.delta.stop_reason;
      }
    } else if(e.type==='message_stop') {
      if(reason===null||![...blocks.values()].every(b=>b.closed))return bad('unsettled_message_stop');
      if(!blocks.size)return bad('empty_response');
      if(reason==='tool_use'&&!toolIds.size)return bad('missing_tool_call');
      stopped=true;
    } else return bad('unsupported_event');
  }
  return stopped?{complete:true,reason:null}:bad('missing_message_stop');
}
