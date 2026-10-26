// Zero-network acceptance against the installed DSH Messages parser.
let calls=0;
globalThis.fetch=async function(){
 if(++calls>4)throw Error('offline fixture request limit');
 const events=[
  {type:'message_start',message:{id:'m',type:'message',role:'assistant',model:'deepseek-flash',content:[],stop_reason:null,usage:{input_tokens:2,output_tokens:0}}},
  {type:'content_block_start',index:0,content_block:{type:'text',text:''}},
  {type:'content_block_delta',index:0,delta:{type:'text_delta',text:'OK'}},
  {type:'content_block_stop',index:0},
  {type:'message_delta',delta:{stop_reason:'end_turn',stop_sequence:null},usage:{output_tokens:1}},
  {type:'message_stop'}
 ];
 const raw=events.map(e=>'event: '+e.type+'\ndata: '+JSON.stringify(e)+'\n\n').join('').trimEnd();
 return new Response(new ReadableStream({start(c){c.enqueue(new TextEncoder().encode(raw));}}),{headers:{'content-type':'text/event-stream'}});
};
