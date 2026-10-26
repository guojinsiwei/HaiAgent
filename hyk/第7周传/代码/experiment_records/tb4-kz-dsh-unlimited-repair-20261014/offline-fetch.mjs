// Acceptance-only preload, NEVER part of the paid runtime archive. Network none.
let count=0;
globalThis.fetch=async(input,init)=>{
  if(String(input)!=='https://api.taotoken.net/token/v1/messages')throw Error('Offline unexpected URL');
  const n=++count;if(n>16)throw Error('Offline fixture exhausted');
  const rows=[];const e=(type,rest={})=>rows.push('event: '+type+'\ndata: '+JSON.stringify({type,...rest})+'\n\n');
  e('message_start',{message:{id:'mock-'+n,type:'message',role:'assistant',model:'deepseek-flash',content:[],usage:{input_tokens:100,output_tokens:0}}});
  let reason;
  if(n<=3){
    e('content_block_start',{index:0,content_block:{type:'tool_use',id:'mock-call-'+n,name:'bash',input:{}}});
    e('content_block_delta',{index:0,delta:{type:'input_json_delta',partial_json:n===2?'{"command":':JSON.stringify({command:n===1?"printf 'WRAPPER_FIRST_OK\\n' | cat":"printf 'WRAPPER_SECOND_OK\\n'",description:'Offline wrapper fixture'})}});reason='tool_use';
  }else{
    e('content_block_start',{index:0,content_block:{type:'text',text:''}});
    e('content_block_delta',{index:0,delta:{type:'text_delta',text:'Done.'}});reason='end_turn';
  }
  e('content_block_stop',{index:0});e('message_delta',{delta:{stop_reason:reason,stop_sequence:null},usage:{output_tokens:20}});e('message_stop');
  return new Response(rows.join(''),{status:200,headers:{'content-type':'text/event-stream'}});
};
