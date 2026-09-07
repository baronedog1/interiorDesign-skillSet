
/* Local, per-parent batching. Never merge across a wall, door, or furniture root.
   Every copied vertex is transformed exactly once into its immediate parent space.
   The editable model is also the displayed/exported model: no second hidden scene. */
(function(C,T){'use strict';
 C.optimizeLocal=function(root){let merged=0;
  function walk(g){for(const c of [...g.children])if(!c.isMesh)walk(c);
   const buckets=new Map();for(const c of g.children){if(!c.isMesh||c.isInstancedMesh||Array.isArray(c.material)||c.material.transparent||c.children.length||c.userData.noExport)continue;
    const k=c.material.uuid+'/'+c.castShadow+'/'+c.receiveShadow;if(!buckets.has(k))buckets.set(k,[]);buckets.get(k).push(c);}
   for(const items of buckets.values()){if(items.length<2)continue;let n=0,nt=0;for(const o of items){n+=o.geometry.attributes.position.count;nt+=o.geometry.index?.count||o.geometry.attributes.position.count;}
    const ps=new Float32Array(n*3),ns=new Float32Array(n*3),uv=new Float32Array(n*2),ix=new Uint32Array(nt);let base=0,j=0;const p=new T.Vector3(),v=new T.Vector3(),nm=new T.Matrix3();
    for(const o of items){o.updateMatrix();const geo=o.geometry,a=geo.attributes.position,b=geo.attributes.normal,t=geo.attributes.uv;nm.getNormalMatrix(o.matrix);
     for(let i=0;i<a.count;i++){p.fromBufferAttribute(a,i).applyMatrix4(o.matrix);ps.set(p.toArray(),(base+i)*3);if(b){v.fromBufferAttribute(b,i).applyMatrix3(nm).normalize();ns.set(v.toArray(),(base+i)*3);}if(t){uv[(base+i)*2]=t.getX(i);uv[(base+i)*2+1]=t.getY(i);}}
     if(geo.index)for(let i=0;i<geo.index.count;i++)ix[j++]=geo.index.getX(i)+base;else for(let i=0;i<a.count;i++)ix[j++]=base+i;base+=a.count;}
    const geo=new T.BufferGeometry();geo.setAttribute('position',new T.BufferAttribute(ps,3));geo.setAttribute('normal',new T.BufferAttribute(ns,3));geo.setAttribute('uv',new T.BufferAttribute(uv,2));geo.setIndex(new T.BufferAttribute(ix,1));geo.computeBoundingBox();geo.computeBoundingSphere();
    const m=new T.Mesh(geo,items[0].material);m.name=items[0].material.name+' / 局部组件';m.castShadow=items[0].castShadow;m.receiveShadow=items[0].receiveShadow;
    items.forEach(o=>g.remove(o));g.add(m);merged+=items.length-1;
   }
  }walk(root);root.updateMatrixWorld(true);C.optimizedMeshes=merged;
 };
})(window.CREAM,window.THREE);

