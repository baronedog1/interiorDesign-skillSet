#!/usr/bin/env node
'use strict';const fs=require('node:fs'),path=require('node:path');const K=require('../assets/workbench/product-kernel.js');
try{if(!process.argv[2])throw Error('用法：node scripts/evaluate.cjs PRODUCT_JSON');const p=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));console.log(JSON.stringify(K.solve(p),null,2));}catch(e){console.error(e.message);process.exit(2);}
