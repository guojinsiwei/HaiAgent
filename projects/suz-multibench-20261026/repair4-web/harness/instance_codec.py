"""JSON encoding of trusted generated task parameters, including official row objects."""
import dataclasses,datetime,importlib

def encode(value):
    if dataclasses.is_dataclass(value):
        return {'__type__':'dataclass','module':type(value).__module__,'name':type(value).__name__,
                'fields':{field.name:encode(getattr(value,field.name)) for field in dataclasses.fields(value) if field.init}}
    if isinstance(value,(datetime.datetime,datetime.date)):
        return {'__type__':type(value).__name__,'value':value.isoformat()}
    if isinstance(value,tuple):return {'__type__':'tuple','items':[encode(x) for x in value]}
    if isinstance(value,list):return [encode(x) for x in value]
    if isinstance(value,dict):return {k:encode(v) for k,v in value.items()}
    if value is None or isinstance(value,(str,int,float,bool)):return value
    if type(value).__module__.startswith('numpy'):return encode(value.item())
    raise TypeError('Unsupported task parameter '+type(value).__name__)

def decode(value):
    if isinstance(value,list):return [decode(x) for x in value]
    if not isinstance(value,dict):return value
    tag=value.get('__type__')
    if tag=='dataclass':
        if not value['module'].startswith('android_world.task_evals.'):raise ValueError('Unapproved parameter class')
        cls=getattr(importlib.import_module(value['module']),value['name'])
        if not dataclasses.is_dataclass(cls):raise ValueError('Parameter class must be a dataclass')
        return cls(**{k:decode(v) for k,v in value['fields'].items()})
    if tag in ['datetime','date']:return getattr(datetime,tag).fromisoformat(value['value'])
    if tag=='tuple':return tuple(decode(x) for x in value['items'])
    if tag:raise ValueError('Unknown parameter encoding')
    return {k:decode(v) for k,v in value.items()}
