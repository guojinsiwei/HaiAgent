export const frame=events=>events.map(e=>'data: '+JSON.stringify(e)+'\n\n').join('');
export function message({tool=false,stop=true,reason=true,closed=true,finalUsage=true,json='{"value":"OK"}'}={}) {
  const events=[{type:'message_start',message:{usage:{input_tokens:8,output_tokens:0}}},
    {type:'content_block_start',index:0,content_block:tool?{type:'tool_use',id:'tool-1',name:'probe_echo',input:{}}:{type:'text',text:'OK'}}];
  if(tool)events.push({type:'content_block_delta',index:0,delta:{type:'input_json_delta',partial_json:json}});
  if(closed)events.push({type:'content_block_stop',index:0});
  events.push({type:'message_delta',delta:reason?{stop_reason:tool?'tool_use':'end_turn'}:{},...(finalUsage?{usage:{output_tokens:2}}:{})});
  if(stop)events.push({type:'message_stop'});
  return frame(events);
}
export const sse=text=>new Response(text,{headers:{'content-type':'text/event-stream'}});
