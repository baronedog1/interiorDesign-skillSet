'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),K=require('../assets/workbench/product-kernel.js');
const source=JSON.parse(fs.readFileSync(path.join(__dirname,'../expected_outcome/cabinet/cabinet.product.json'),'utf8'));let checks=[];
function test(name,fn){fn();checks.push({name,pass:true});}
function changed(fn){let s=structuredClone(source);fn(s);return s;}
test('default cabinet 17 parts',()=>assert.equal(K.solve(source).parts.length,17));
test('open cabinet 13 parts',()=>assert.equal(K.solve(source,{variant:'open'}).parts.length,13));
test('drawer variant swaps fronts',()=>{let s=K.solve(source,{variant:'drawers'});assert(s.parts.some(p=>p.id.includes('drawer')));assert(!s.parts.some(p=>p.id==='door-left'));});
test('width changes inner span, not thickness',()=>{let s=K.solve(source,{width:1000});assert.equal(s.derived.inner,964);assert.equal(s.parts.find(p=>p.id==='side-left').size_mm[0],18);});
test('shelf follows documented interpretation',()=>assert.equal(K.solve(source).derived.shelf_width,763));
test('out of range rejected',()=>assert.throws(()=>K.solve(source,{width:0})));
test('unknown parameter rejected',()=>assert.throws(()=>K.solve(source,{secret:1})));
test('bad numeric rejected',()=>assert.throws(()=>K.solve(source,{width:NaN})));
test('unknown variant rejected',()=>assert.throws(()=>K.solve(source,{variant:'unknown'})));
test('non-HEX color rejected',()=>assert.throws(()=>K.solve(source,{finish:'red'})));
test('raw code expression rejected',()=>assert.throws(()=>K.expr('alert(1)',{})));
test('unknown reference rejected',()=>assert.throws(()=>K.expr(['ref','missing'],{})));
test('divide by zero rejected',()=>assert.throws(()=>K.expr(['/',1,0],{})));
test('duplicate parts rejected',()=>assert.throws(()=>K.solve(changed(s=>s.parts.push(s.parts[0])))));
test('assembly cycle rejected',()=>assert.throws(()=>K.solve(changed(s=>s.assemblies[0].parent=s.assemblies[0].id))));
test('invalid offset rejected',()=>assert.throws(()=>K.solve(changed(s=>s.edits={'side-left':{offset_mm:[Infinity,0,0]}}))));
test('roughness outside physical range rejected',()=>assert.throws(()=>K.solve(changed(s=>s.edits={'side-left':{roughness:2}}))));
test('input definition not mutated',()=>{let before=JSON.stringify(source);K.solve(source,{width:1000});assert.equal(JSON.stringify(source),before);});
console.log(JSON.stringify({ok:true,passed:checks.length,checks},null,2));
