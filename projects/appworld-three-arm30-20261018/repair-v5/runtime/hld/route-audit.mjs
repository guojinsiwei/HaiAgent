// Integrity validation retained; no request quota, guessed bill or raw prompts.
import {appendFileSync} from 'node:fs';
const nativeFetch=globalThis.fetch;
const expected=process.env.DSH_EXPECT_ENDPOINT??'https://api.taotoken.net/token/v1/messages';
let count=0;
const record=data=>appendFileSync(process.env.DSH_ROUTE_AUDIT,JSON.stringify({time:new Date().toISOString(),...data})+'\n');
globalThis.fetch=async function(input,init){
  const url=typeof input==='string'?input:input instanceof URL?input.href:input.url;
  const headers=new Headers(init?.headers??(input instanceof Request?input.headers:undefined));
  const keyMatchesInput=Boolean(process.env.TAOTOKEN_API_KEY)&&headers.get('x-api-key')===process.env.TAOTOKEN_API_KEY;
  const endpointMatches=url===expected,attempt=++count;
  record({event:'request',attempt,endpointMatches,keyMatchesInput});
  if(!endpointMatches||!keyMatchesInput)throw Error('DSH route/key integrity check failed');
  let body;try{body=JSON.parse(init?.body);}catch{throw Error('Expected JSON Messages request');}
  if(body.model!=='deepseek-flash'||body.stream!==true)throw Error('Unexpected model or non-streaming DSH request');
  record({event:'request_shape',attempt,model:body.model,stream:body.stream,max_tokens:body.max_tokens,temperature:body.temperature,thinking:body.thinking?.type,tool_count:body.tools?.length??0});
  try{const response=await nativeFetch(input,{...init,redirect:'error'});record({event:'response',attempt,status:response.status});return response;}
  catch(error){record({event:'transport_error',attempt,error_type:error.name});throw error;}
};
