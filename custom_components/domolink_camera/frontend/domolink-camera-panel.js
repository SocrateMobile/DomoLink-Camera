/* DomoLink Camera - Integrated QR Code Engine */
if (typeof window !== "undefined" && !window.QRCode) {
var QRCode;!function(){function a(a){this.mode=c.MODE_8BIT_BYTE,this.data=a,this.parsedData=[];for(var b=[],d=0,e=this.data.length;e>d;d++){var f=this.data.charCodeAt(d);f>65536?(b[0]=240|(1835008&f)>>>18,b[1]=128|(258048&f)>>>12,b[2]=128|(4032&f)>>>6,b[3]=128|63&f):f>2048?(b[0]=224|(61440&f)>>>12,b[1]=128|(4032&f)>>>6,b[2]=128|63&f):f>128?(b[0]=192|(1984&f)>>>6,b[1]=128|63&f):b[0]=f,this.parsedData=this.parsedData.concat(b)}this.parsedData.length!=this.data.length&&(this.parsedData.unshift(191),this.parsedData.unshift(187),this.parsedData.unshift(239))}function b(a,b){this.typeNumber=a,this.errorCorrectLevel=b,this.modules=null,this.moduleCount=0,this.dataCache=null,this.dataList=[]}function i(a,b){if(void 0==a.length)throw new Error(a.length+"/"+b);for(var c=0;c<a.length&&0==a[c];)c++;this.num=new Array(a.length-c+b);for(var d=0;d<a.length-c;d++)this.num[d]=a[d+c]}function j(a,b){this.totalCount=a,this.dataCount=b}function k(){this.buffer=[],this.length=0}function m(){return"undefined"!=typeof CanvasRenderingContext2D}function n(){var a=!1,b=navigator.userAgent;return/android/i.test(b)&&(a=!0,aMat=b.toString().match(/android ([0-9]\.[0-9])/i),aMat&&aMat[1]&&(a=parseFloat(aMat[1]))),a}function r(a,b){for(var c=1,e=s(a),f=0,g=l.length;g>=f;f++){var h=0;switch(b){case d.L:h=l[f][0];break;case d.M:h=l[f][1];break;case d.Q:h=l[f][2];break;case d.H:h=l[f][3]}if(h>=e)break;c++}if(c>l.length)throw new Error("Too long data");return c}function s(a){var b=encodeURI(a).toString().replace(/\%[0-9a-fA-F]{2}/g,"a");return b.length+(b.length!=a?3:0)}a.prototype={getLength:function(){return this.parsedData.length},write:function(a){for(var b=0,c=this.parsedData.length;c>b;b++)a.put(this.parsedData[b],8)}},b.prototype={addData:function(b){var c=new a(b);this.dataList.push(c),this.dataCache=null},isDark:function(a,b){if(0>a||this.moduleCount<=a||0>b||this.moduleCount<=b)throw new Error(a+","+b);return this.modules[a][b]},getModuleCount:function(){return this.moduleCount},make:function(){this.makeImpl(!1,this.getBestMaskPattern())},makeImpl:function(a,c){this.moduleCount=4*this.typeNumber+17,this.modules=new Array(this.moduleCount);for(var d=0;d<this.moduleCount;d++){this.modules[d]=new Array(this.moduleCount);for(var e=0;e<this.moduleCount;e++)this.modules[d][e]=null}this.setupPositionProbePattern(0,0),this.setupPositionProbePattern(this.moduleCount-7,0),this.setupPositionProbePattern(0,this.moduleCount-7),this.setupPositionAdjustPattern(),this.setupTimingPattern(),this.setupTypeInfo(a,c),this.typeNumber>=7&&this.setupTypeNumber(a),null==this.dataCache&&(this.dataCache=b.createData(this.typeNumber,this.errorCorrectLevel,this.dataList)),this.mapData(this.dataCache,c)},setupPositionProbePattern:function(a,b){for(var c=-1;7>=c;c++)if(!(-1>=a+c||this.moduleCount<=a+c))for(var d=-1;7>=d;d++)-1>=b+d||this.moduleCount<=b+d||(this.modules[a+c][b+d]=c>=0&&6>=c&&(0==d||6==d)||d>=0&&6>=d&&(0==c||6==c)||c>=2&&4>=c&&d>=2&&4>=d?!0:!1)},getBestMaskPattern:function(){for(var a=0,b=0,c=0;8>c;c++){this.makeImpl(!0,c);var d=f.getLostPoint(this);(0==c||a>d)&&(a=d,b=c)}return b},createMovieClip:function(a,b,c){var d=a.createEmptyMovieClip(b,c),e=1;this.make();for(var f=0;f<this.modules.length;f++)for(var g=f*e,h=0;h<this.modules[f].length;h++){var i=h*e,j=this.modules[f][h];j&&(d.beginFill(0,100),d.moveTo(i,g),d.lineTo(i+e,g),d.lineTo(i+e,g+e),d.lineTo(i,g+e),d.endFill())}return d},setupTimingPattern:function(){for(var a=8;a<this.moduleCount-8;a++)null==this.modules[a][6]&&(this.modules[a][6]=0==a%2);for(var b=8;b<this.moduleCount-8;b++)null==this.modules[6][b]&&(this.modules[6][b]=0==b%2)},setupPositionAdjustPattern:function(){for(var a=f.getPatternPosition(this.typeNumber),b=0;b<a.length;b++)for(var c=0;c<a.length;c++){var d=a[b],e=a[c];if(null==this.modules[d][e])for(var g=-2;2>=g;g++)for(var h=-2;2>=h;h++)this.modules[d+g][e+h]=-2==g||2==g||-2==h||2==h||0==g&&0==h?!0:!1}},setupTypeNumber:function(a){for(var b=f.getBCHTypeNumber(this.typeNumber),c=0;18>c;c++){var d=!a&&1==(1&b>>c);this.modules[Math.floor(c/3)][c%3+this.moduleCount-8-3]=d}for(var c=0;18>c;c++){var d=!a&&1==(1&b>>c);this.modules[c%3+this.moduleCount-8-3][Math.floor(c/3)]=d}},setupTypeInfo:function(a,b){for(var c=this.errorCorrectLevel<<3|b,d=f.getBCHTypeInfo(c),e=0;15>e;e++){var g=!a&&1==(1&d>>e);6>e?this.modules[e][8]=g:8>e?this.modules[e+1][8]=g:this.modules[this.moduleCount-15+e][8]=g}for(var e=0;15>e;e++){var g=!a&&1==(1&d>>e);8>e?this.modules[8][this.moduleCount-e-1]=g:9>e?this.modules[8][15-e-1+1]=g:this.modules[8][15-e-1]=g}this.modules[this.moduleCount-8][8]=!a},mapData:function(a,b){for(var c=-1,d=this.moduleCount-1,e=7,g=0,h=this.moduleCount-1;h>0;h-=2)for(6==h&&h--;;){for(var i=0;2>i;i++)if(null==this.modules[d][h-i]){var j=!1;g<a.length&&(j=1==(1&a[g]>>>e));var k=f.getMask(b,d,h-i);k&&(j=!j),this.modules[d][h-i]=j,e--,-1==e&&(g++,e=7)}if(d+=c,0>d||this.moduleCount<=d){d-=c,c=-c;break}}}},b.PAD0=236,b.PAD1=17,b.createData=function(a,c,d){for(var e=j.getRSBlocks(a,c),g=new k,h=0;h<d.length;h++){var i=d[h];g.put(i.mode,4),g.put(i.getLength(),f.getLengthInBits(i.mode,a)),i.write(g)}for(var l=0,h=0;h<e.length;h++)l+=e[h].dataCount;if(g.getLengthInBits()>8*l)throw new Error("code length overflow. ("+g.getLengthInBits()+">"+8*l+")");for(g.getLengthInBits()+4<=8*l&&g.put(0,4);0!=g.getLengthInBits()%8;)g.putBit(!1);for(;;){if(g.getLengthInBits()>=8*l)break;if(g.put(b.PAD0,8),g.getLengthInBits()>=8*l)break;g.put(b.PAD1,8)}return b.createBytes(g,e)},b.createBytes=function(a,b){for(var c=0,d=0,e=0,g=new Array(b.length),h=new Array(b.length),j=0;j<b.length;j++){var k=b[j].dataCount,l=b[j].totalCount-k;d=Math.max(d,k),e=Math.max(e,l),g[j]=new Array(k);for(var m=0;m<g[j].length;m++)g[j][m]=255&a.buffer[m+c];c+=k;var n=f.getErrorCorrectPolynomial(l),o=new i(g[j],n.getLength()-1),p=o.mod(n);h[j]=new Array(n.getLength()-1);for(var m=0;m<h[j].length;m++){var q=m+p.getLength()-h[j].length;h[j][m]=q>=0?p.get(q):0}}for(var r=0,m=0;m<b.length;m++)r+=b[m].totalCount;for(var s=new Array(r),t=0,m=0;d>m;m++)for(var j=0;j<b.length;j++)m<g[j].length&&(s[t++]=g[j][m]);for(var m=0;e>m;m++)for(var j=0;j<b.length;j++)m<h[j].length&&(s[t++]=h[j][m]);return s};for(var c={MODE_NUMBER:1,MODE_ALPHA_NUM:2,MODE_8BIT_BYTE:4,MODE_KANJI:8},d={L:1,M:0,Q:3,H:2},e={PATTERN000:0,PATTERN001:1,PATTERN010:2,PATTERN011:3,PATTERN100:4,PATTERN101:5,PATTERN110:6,PATTERN111:7},f={PATTERN_POSITION_TABLE:[[],[6,18],[6,22],[6,26],[6,30],[6,34],[6,22,38],[6,24,42],[6,26,46],[6,28,50],[6,30,54],[6,32,58],[6,34,62],[6,26,46,66],[6,26,48,70],[6,26,50,74],[6,30,54,78],[6,30,56,82],[6,30,58,86],[6,34,62,90],[6,28,50,72,94],[6,26,50,74,98],[6,30,54,78,102],[6,28,54,80,106],[6,32,58,84,110],[6,30,58,86,114],[6,34,62,90,118],[6,26,50,74,98,122],[6,30,54,78,102,126],[6,26,52,78,104,130],[6,30,56,82,108,134],[6,34,60,86,112,138],[6,30,58,86,114,142],[6,34,62,90,118,146],[6,30,54,78,102,126,150],[6,24,50,76,102,128,154],[6,28,54,80,106,132,158],[6,32,58,84,110,136,162],[6,26,54,82,110,138,166],[6,30,58,86,114,142,170]],G15:1335,G18:7973,G15_MASK:21522,getBCHTypeInfo:function(a){for(var b=a<<10;f.getBCHDigit(b)-f.getBCHDigit(f.G15)>=0;)b^=f.G15<<f.getBCHDigit(b)-f.getBCHDigit(f.G15);return(a<<10|b)^f.G15_MASK},getBCHTypeNumber:function(a){for(var b=a<<12;f.getBCHDigit(b)-f.getBCHDigit(f.G18)>=0;)b^=f.G18<<f.getBCHDigit(b)-f.getBCHDigit(f.G18);return a<<12|b},getBCHDigit:function(a){for(var b=0;0!=a;)b++,a>>>=1;return b},getPatternPosition:function(a){return f.PATTERN_POSITION_TABLE[a-1]},getMask:function(a,b,c){switch(a){case e.PATTERN000:return 0==(b+c)%2;case e.PATTERN001:return 0==b%2;case e.PATTERN010:return 0==c%3;case e.PATTERN011:return 0==(b+c)%3;case e.PATTERN100:return 0==(Math.floor(b/2)+Math.floor(c/3))%2;case e.PATTERN101:return 0==b*c%2+b*c%3;case e.PATTERN110:return 0==(b*c%2+b*c%3)%2;case e.PATTERN111:return 0==(b*c%3+(b+c)%2)%2;default:throw new Error("bad maskPattern:"+a)}},getErrorCorrectPolynomial:function(a){for(var b=new i([1],0),c=0;a>c;c++)b=b.multiply(new i([1,g.gexp(c)],0));return b},getLengthInBits:function(a,b){if(b>=1&&10>b)switch(a){case c.MODE_NUMBER:return 10;case c.MODE_ALPHA_NUM:return 9;case c.MODE_8BIT_BYTE:return 8;case c.MODE_KANJI:return 8;default:throw new Error("mode:"+a)}else if(27>b)switch(a){case c.MODE_NUMBER:return 12;case c.MODE_ALPHA_NUM:return 11;case c.MODE_8BIT_BYTE:return 16;case c.MODE_KANJI:return 10;default:throw new Error("mode:"+a)}else{if(!(41>b))throw new Error("type:"+b);switch(a){case c.MODE_NUMBER:return 14;case c.MODE_ALPHA_NUM:return 13;case c.MODE_8BIT_BYTE:return 16;case c.MODE_KANJI:return 12;default:throw new Error("mode:"+a)}}},getLostPoint:function(a){for(var b=a.getModuleCount(),c=0,d=0;b>d;d++)for(var e=0;b>e;e++){for(var f=0,g=a.isDark(d,e),h=-1;1>=h;h++)if(!(0>d+h||d+h>=b))for(var i=-1;1>=i;i++)0>e+i||e+i>=b||(0!=h||0!=i)&&g==a.isDark(d+h,e+i)&&f++;f>5&&(c+=3+f-5)}for(var d=0;b-1>d;d++)for(var e=0;b-1>e;e++){var j=0;a.isDark(d,e)&&j++,a.isDark(d+1,e)&&j++,a.isDark(d,e+1)&&j++,a.isDark(d+1,e+1)&&j++,(0==j||4==j)&&(c+=3)}for(var d=0;b>d;d++)for(var e=0;b-6>e;e++)a.isDark(d,e)&&!a.isDark(d,e+1)&&a.isDark(d,e+2)&&a.isDark(d,e+3)&&a.isDark(d,e+4)&&!a.isDark(d,e+5)&&a.isDark(d,e+6)&&(c+=40);for(var e=0;b>e;e++)for(var d=0;b-6>d;d++)a.isDark(d,e)&&!a.isDark(d+1,e)&&a.isDark(d+2,e)&&a.isDark(d+3,e)&&a.isDark(d+4,e)&&!a.isDark(d+5,e)&&a.isDark(d+6,e)&&(c+=40);for(var k=0,e=0;b>e;e++)for(var d=0;b>d;d++)a.isDark(d,e)&&k++;var l=Math.abs(100*k/b/b-50)/5;return c+=10*l}},g={glog:function(a){if(1>a)throw new Error("glog("+a+")");return g.LOG_TABLE[a]},gexp:function(a){for(;0>a;)a+=255;for(;a>=256;)a-=255;return g.EXP_TABLE[a]},EXP_TABLE:new Array(256),LOG_TABLE:new Array(256)},h=0;8>h;h++)g.EXP_TABLE[h]=1<<h;for(var h=8;256>h;h++)g.EXP_TABLE[h]=g.EXP_TABLE[h-4]^g.EXP_TABLE[h-5]^g.EXP_TABLE[h-6]^g.EXP_TABLE[h-8];for(var h=0;255>h;h++)g.LOG_TABLE[g.EXP_TABLE[h]]=h;i.prototype={get:function(a){return this.num[a]},getLength:function(){return this.num.length},multiply:function(a){for(var b=new Array(this.getLength()+a.getLength()-1),c=0;c<this.getLength();c++)for(var d=0;d<a.getLength();d++)b[c+d]^=g.gexp(g.glog(this.get(c))+g.glog(a.get(d)));return new i(b,0)},mod:function(a){if(this.getLength()-a.getLength()<0)return this;for(var b=g.glog(this.get(0))-g.glog(a.get(0)),c=new Array(this.getLength()),d=0;d<this.getLength();d++)c[d]=this.get(d);for(var d=0;d<a.getLength();d++)c[d]^=g.gexp(g.glog(a.get(d))+b);return new i(c,0).mod(a)}},j.RS_BLOCK_TABLE=[[1,26,19],[1,26,16],[1,26,13],[1,26,9],[1,44,34],[1,44,28],[1,44,22],[1,44,16],[1,70,55],[1,70,44],[2,35,17],[2,35,13],[1,100,80],[2,50,32],[2,50,24],[4,25,9],[1,134,108],[2,67,43],[2,33,15,2,34,16],[2,33,11,2,34,12],[2,86,68],[4,43,27],[4,43,19],[4,43,15],[2,98,78],[4,49,31],[2,32,14,4,33,15],[4,39,13,1,40,14],[2,121,97],[2,60,38,2,61,39],[4,40,18,2,41,19],[4,40,14,2,41,15],[2,146,116],[3,58,36,2,59,37],[4,36,16,4,37,17],[4,36,12,4,37,13],[2,86,68,2,87,69],[4,69,43,1,70,44],[6,43,19,2,44,20],[6,43,15,2,44,16],[4,101,81],[1,80,50,4,81,51],[4,50,22,4,51,23],[3,36,12,8,37,13],[2,116,92,2,117,93],[6,58,36,2,59,37],[4,46,20,6,47,21],[7,42,14,4,43,15],[4,133,107],[8,59,37,1,60,38],[8,44,20,4,45,21],[12,33,11,4,34,12],[3,145,115,1,146,116],[4,64,40,5,65,41],[11,36,16,5,37,17],[11,36,12,5,37,13],[5,109,87,1,110,88],[5,65,41,5,66,42],[5,54,24,7,55,25],[11,36,12],[5,122,98,1,123,99],[7,73,45,3,74,46],[15,43,19,2,44,20],[3,45,15,13,46,16],[1,135,107,5,136,108],[10,74,46,1,75,47],[1,50,22,15,51,23],[2,42,14,17,43,15],[5,150,120,1,151,121],[9,69,43,4,70,44],[17,50,22,1,51,23],[2,42,14,19,43,15],[3,141,113,4,142,114],[3,70,44,11,71,45],[17,47,21,4,48,22],[9,39,13,16,40,14],[3,135,107,5,136,108],[3,67,41,13,68,42],[15,54,24,5,55,25],[15,43,15,10,44,16],[4,144,116,4,145,117],[17,68,42],[17,50,22,6,51,23],[19,46,16,6,47,17],[2,139,111,7,140,112],[17,74,46],[7,54,24,16,55,25],[34,37,13],[4,151,121,5,152,122],[4,75,47,14,76,48],[11,54,24,14,55,25],[16,45,15,14,46,16],[6,147,117,4,148,118],[6,73,45,14,74,46],[11,54,24,16,55,25],[30,46,16,2,47,17],[8,132,106,4,133,107],[8,75,47,13,76,48],[7,54,24,22,55,25],[22,45,15,13,46,16],[10,142,114,2,143,115],[19,74,46,4,75,47],[28,50,22,6,51,23],[33,46,16,4,47,17],[8,152,122,4,153,123],[22,73,45,3,74,46],[8,53,23,26,54,24],[12,45,15,28,46,16],[3,147,117,10,148,118],[3,73,45,23,74,46],[4,54,24,31,55,25],[11,45,15,31,46,16],[7,146,116,7,147,117],[21,73,45,7,74,46],[1,53,23,37,54,24],[19,45,15,26,46,16],[5,145,115,10,146,116],[19,75,47,10,76,48],[15,54,24,25,55,25],[23,45,15,25,46,16],[13,145,115,3,146,116],[2,74,46,29,75,47],[42,54,24,1,55,25],[23,45,15,28,46,16],[17,145,115],[10,74,46,23,75,47],[10,54,24,35,55,25],[19,45,15,35,46,16],[17,145,115,1,146,116],[14,74,46,21,75,47],[29,54,24,19,55,25],[11,45,15,46,46,16],[13,145,115,6,146,116],[14,74,46,23,75,47],[44,54,24,7,55,25],[59,46,16,1,47,17],[12,151,121,7,152,122],[12,75,47,26,76,48],[39,54,24,14,55,25],[22,45,15,41,46,16],[6,151,121,14,152,122],[6,75,47,34,76,48],[46,54,24,10,55,25],[2,45,15,64,46,16],[17,152,122,4,153,123],[29,74,46,14,75,47],[49,54,24,10,55,25],[24,45,15,46,46,16],[4,152,122,18,153,123],[13,74,46,32,75,47],[48,54,24,14,55,25],[42,45,15,32,46,16],[20,147,117,4,148,118],[40,75,47,7,76,48],[43,54,24,22,55,25],[10,45,15,67,46,16],[19,148,118,6,149,119],[18,75,47,31,76,48],[34,54,24,34,55,25],[20,45,15,61,46,16]],j.getRSBlocks=function(a,b){var c=j.getRsBlockTable(a,b);if(void 0==c)throw new Error("bad rs block @ typeNumber:"+a+"/errorCorrectLevel:"+b);for(var d=c.length/3,e=[],f=0;d>f;f++)for(var g=c[3*f+0],h=c[3*f+1],i=c[3*f+2],k=0;g>k;k++)e.push(new j(h,i));return e},j.getRsBlockTable=function(a,b){switch(b){case d.L:return j.RS_BLOCK_TABLE[4*(a-1)+0];case d.M:return j.RS_BLOCK_TABLE[4*(a-1)+1];case d.Q:return j.RS_BLOCK_TABLE[4*(a-1)+2];case d.H:return j.RS_BLOCK_TABLE[4*(a-1)+3];default:return void 0}},k.prototype={get:function(a){var b=Math.floor(a/8);return 1==(1&this.buffer[b]>>>7-a%8)},put:function(a,b){for(var c=0;b>c;c++)this.putBit(1==(1&a>>>b-c-1))},getLengthInBits:function(){return this.length},putBit:function(a){var b=Math.floor(this.length/8);this.buffer.length<=b&&this.buffer.push(0),a&&(this.buffer[b]|=128>>>this.length%8),this.length++}};var l=[[17,14,11,7],[32,26,20,14],[53,42,32,24],[78,62,46,34],[106,84,60,44],[134,106,74,58],[154,122,86,64],[192,152,108,84],[230,180,130,98],[271,213,151,119],[321,251,177,137],[367,287,203,155],[425,331,241,177],[458,362,258,194],[520,412,292,220],[586,450,322,250],[644,504,364,280],[718,560,394,310],[792,624,442,338],[858,666,482,382],[929,711,509,403],[1003,779,565,439],[1091,857,611,461],[1171,911,661,511],[1273,997,715,535],[1367,1059,751,593],[1465,1125,805,625],[1528,1190,868,658],[1628,1264,908,698],[1732,1370,982,742],[1840,1452,1030,790],[1952,1538,1112,842],[2068,1628,1168,898],[2188,1722,1228,958],[2303,1809,1283,983],[2431,1911,1351,1051],[2563,1989,1423,1093],[2699,2099,1499,1139],[2809,2213,1579,1219],[2953,2331,1663,1273]],o=function(){var a=function(a,b){this._el=a,this._htOption=b};return a.prototype.draw=function(a){function g(a,b){var c=document.createElementNS("http://www.w3.org/2000/svg",a);for(var d in b)b.hasOwnProperty(d)&&c.setAttribute(d,b[d]);return c}var b=this._htOption,c=this._el,d=a.getModuleCount();Math.floor(b.width/d),Math.floor(b.height/d),this.clear();var h=g("svg",{viewBox:"0 0 "+String(d)+" "+String(d),width:"100%",height:"100%",fill:b.colorLight});h.setAttributeNS("http://www.w3.org/2000/xmlns/","xmlns:xlink","http://www.w3.org/1999/xlink"),c.appendChild(h),h.appendChild(g("rect",{fill:b.colorDark,width:"1",height:"1",id:"template"}));for(var i=0;d>i;i++)for(var j=0;d>j;j++)if(a.isDark(i,j)){var k=g("use",{x:String(i),y:String(j)});k.setAttributeNS("http://www.w3.org/1999/xlink","href","#template"),h.appendChild(k)}},a.prototype.clear=function(){for(;this._el.hasChildNodes();)this._el.removeChild(this._el.lastChild)},a}(),p="svg"===document.documentElement.tagName.toLowerCase(),q=p?o:m()?function(){function a(){this._elImage.src=this._elCanvas.toDataURL("image/png"),this._elImage.style.display="block",this._elCanvas.style.display="none"}function d(a,b){var c=this;if(c._fFail=b,c._fSuccess=a,null===c._bSupportDataURI){var d=document.createElement("img"),e=function(){c._bSupportDataURI=!1,c._fFail&&_fFail.call(c)},f=function(){c._bSupportDataURI=!0,c._fSuccess&&c._fSuccess.call(c)};return d.onabort=e,d.onerror=e,d.onload=f,d.src="data:image/gif;base64,iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg==",void 0}c._bSupportDataURI===!0&&c._fSuccess?c._fSuccess.call(c):c._bSupportDataURI===!1&&c._fFail&&c._fFail.call(c)}if(this._android&&this._android<=2.1){var b=1/window.devicePixelRatio,c=CanvasRenderingContext2D.prototype.drawImage;CanvasRenderingContext2D.prototype.drawImage=function(a,d,e,f,g,h,i,j){if("nodeName"in a&&/img/i.test(a.nodeName))for(var l=arguments.length-1;l>=1;l--)arguments[l]=arguments[l]*b;else"undefined"==typeof j&&(arguments[1]*=b,arguments[2]*=b,arguments[3]*=b,arguments[4]*=b);c.apply(this,arguments)}}var e=function(a,b){this._bIsPainted=!1,this._android=n(),this._htOption=b,this._elCanvas=document.createElement("canvas"),this._elCanvas.width=b.width,this._elCanvas.height=b.height,a.appendChild(this._elCanvas),this._el=a,this._oContext=this._elCanvas.getContext("2d"),this._bIsPainted=!1,this._elImage=document.createElement("img"),this._elImage.style.display="none",this._el.appendChild(this._elImage),this._bSupportDataURI=null};return e.prototype.draw=function(a){var b=this._elImage,c=this._oContext,d=this._htOption,e=a.getModuleCount(),f=d.width/e,g=d.height/e,h=Math.round(f),i=Math.round(g);b.style.display="none",this.clear();for(var j=0;e>j;j++)for(var k=0;e>k;k++){var l=a.isDark(j,k),m=k*f,n=j*g;c.strokeStyle=l?d.colorDark:d.colorLight,c.lineWidth=1,c.fillStyle=l?d.colorDark:d.colorLight,c.fillRect(m,n,f,g),c.strokeRect(Math.floor(m)+.5,Math.floor(n)+.5,h,i),c.strokeRect(Math.ceil(m)-.5,Math.ceil(n)-.5,h,i)}this._bIsPainted=!0},e.prototype.makeImage=function(){this._bIsPainted&&d.call(this,a)},e.prototype.isPainted=function(){return this._bIsPainted},e.prototype.clear=function(){this._oContext.clearRect(0,0,this._elCanvas.width,this._elCanvas.height),this._bIsPainted=!1},e.prototype.round=function(a){return a?Math.floor(1e3*a)/1e3:a},e}():function(){var a=function(a,b){this._el=a,this._htOption=b};return a.prototype.draw=function(a){for(var b=this._htOption,c=this._el,d=a.getModuleCount(),e=Math.floor(b.width/d),f=Math.floor(b.height/d),g=['<table style="border:0;border-collapse:collapse;">'],h=0;d>h;h++){g.push("<tr>");for(var i=0;d>i;i++)g.push('<td style="border:0;border-collapse:collapse;padding:0;margin:0;width:'+e+"px;height:"+f+"px;background-color:"+(a.isDark(h,i)?b.colorDark:b.colorLight)+';"></td>');g.push("</tr>")}g.push("</table>"),c.innerHTML=g.join("");var j=c.childNodes[0],k=(b.width-j.offsetWidth)/2,l=(b.height-j.offsetHeight)/2;k>0&&l>0&&(j.style.margin=l+"px "+k+"px")},a.prototype.clear=function(){this._el.innerHTML=""},a}();QRCode=function(a,b){if(this._htOption={width:256,height:256,typeNumber:4,colorDark:"#000000",colorLight:"#ffffff",correctLevel:d.H},"string"==typeof b&&(b={text:b}),b)for(var c in b)this._htOption[c]=b[c];"string"==typeof a&&(a=document.getElementById(a)),this._android=n(),this._el=a,this._oQRCode=null,this._oDrawing=new q(this._el,this._htOption),this._htOption.text&&this.makeCode(this._htOption.text)},QRCode.prototype.makeCode=function(a){this._oQRCode=new b(r(a,this._htOption.correctLevel),this._htOption.correctLevel),this._oQRCode.addData(a),this._oQRCode.make(),this._el.title=a,this._oDrawing.draw(this._oQRCode),this.makeImage()},QRCode.prototype.makeImage=function(){"function"==typeof this._oDrawing.makeImage&&(!this._android||this._android>=3)&&this._oDrawing.makeImage()},QRCode.prototype.clear=function(){this._oDrawing.clear()},QRCode.CorrectLevel=d}();
  window.QRCode = QRCode;
}

/**
 * DomoLink-Camera Custom Panel for Home Assistant
 * Modern glassmorphism UI matching Domolink-Alarm design language
 */

class DomolinkCameraPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._cameras = [];
    this._availableEntities = [];
    this._activeTab = "cameras"; // "cameras" or "settings"
    this._liveCameras = new Set();
    this._draggedIndex = null;
    this._hasUnsavedOrder = false;
    this._pairingActive = false;
    this._pairingLogs = [];
    try {
      this._pairSsid = localStorage.getItem("domolink_pair_ssid") || "";
      this._pairPass = localStorage.getItem("domolink_pair_pass") || "";
      this._pairApIp = localStorage.getItem("domolink_pair_ap_ip") || "192.168.1.1";
    } catch (e) {
      this._pairSsid = "";
      this._pairPass = "";
      this._pairApIp = "192.168.1.1";
    }
    this._pollTimer = null;
    this._detectedAps = [];
    this._selectedCameraAp = null;
    this._showQrCode = false;
    this._scanResults = [];
    this._scanCompatible = [];
    this._scanIncompatible = [];
    this._scanSummary = null;
    this._isScanning = false;
    this._selectedCamera = null;
    this._refreshTimer = null;
    this._toastMsg = null;
    this._boxInfo = null;
    this._tvChannels = [];
    this._selectedChannel = null;
    this._tvSearch = "";
    this._tvFilter = "all";
    this._hlsPlayer = null;
    this._isLoadingTv = false;
  }

  set panel(panel) {
    this._panel = panel;
  }

  set hass(hass) {
    const isFirst = !this._hass;
    this._hass = hass;
    this._fetchAvailableEntities();
    if (isFirst) {
      this._init();
    } else {
      this._updateEntitiesState();
    }
  }

  connectedCallback() {
    this.render();
    this._startPeriodicRefresh();
  }

  disconnectedCallback() {
    this._stopPeriodicRefresh();
  }

  async _init() {
    this.render();
    try {
      await this._fetchCameras();
    } catch (e) {
      console.error("[DomoLink-Camera] Error fetching cameras:", e);
    }
    this.render();
  }

  _startPeriodicRefresh() {
    this._stopPeriodicRefresh();
    // Refresh snapshot timestamps / status every 8 seconds if in cameras tab
    this._refreshTimer = setInterval(() => {
      if (this._activeTab === "cameras") {
        this._fetchCameras(false);
      }
    }, 8000);
  }

  _stopPeriodicRefresh() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = null;
    }
  }

  async _fetchCameras(renderAfter = true) {
    if (!this._hass) return;
    try {
      const resp = await this._hass.callWS({ type: "domolink_camera/get_cameras" });
      if (resp && resp.cameras) {
        this._cameras = resp.cameras;
        if (renderAfter) this.render();
      }
    } catch (e) {
      console.error("[DomoLink-Camera] Failed to fetch cameras:", e);
    }
  }

  _fetchAvailableEntities() {
    if (!this._hass || !this._hass.states) return;
    try {
      const allowed = ["switch", "light", "cover", "lock", "fan"];
      this._availableEntities = Object.values(this._hass.states)
        .filter((s) => allowed.includes(s.entity_id.split(".")[0]))
        .slice(0, 150)
        .map((s) => ({
          entity_id: s.entity_id,
          name: s.attributes.friendly_name || s.entity_id,
        }))
        .sort((a, b) => a.name.localeCompare(b.name));
    } catch (e) {
      this._availableEntities = [];
    }
  }

  _updateEntitiesState() {
    // Light live refresh of entities in bottom banners
    const strips = this.shadowRoot.querySelectorAll(".entity-badge");
    strips.forEach((el) => {
      const entityId = el.dataset.entityId;
      const stateObj = this._hass.states[entityId];
      if (stateObj) {
        const valEl = el.querySelector(".badge-state");
        if (valEl) {
          const unit = stateObj.attributes.unit_of_measurement || "";
          valEl.textContent = `${stateObj.state} ${unit}`.trim();
        }
        if (stateObj.state === "on") {
          el.classList.add("active");
        } else {
          el.classList.remove("active");
        }
      }
    });
  }

  _showToast(msg, duration = 3000) {
    this._toastMsg = msg;
    const toast = this.shadowRoot.querySelector(".toast-bar");
    if (toast) {
      toast.textContent = msg;
      toast.classList.add("show");
      setTimeout(() => {
        toast.classList.remove("show");
      }, duration);
    }
  }

  // --- Drag and Drop Handlers ---
  _handleDragStart(e, index) {
    this._draggedIndex = index;
    e.dataTransfer.effectAllowed = "move";
    e.target.classList.add("dragging");
  }

  _handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }

  _handleDragEnter(e) {
    const card = e.target.closest(".camera-card");
    if (card) card.classList.add("drag-over");
  }

  _handleDragLeave(e) {
    const card = e.target.closest(".camera-card");
    if (card) card.classList.remove("drag-over");
  }

  _handleDrop(e, targetIndex) {
    e.preventDefault();
    const card = e.target.closest(".camera-card");
    if (card) card.classList.remove("drag-over");

    if (this._draggedIndex !== null && this._draggedIndex !== targetIndex) {
      const movedItem = this._cameras.splice(this._draggedIndex, 1)[0];
      this._cameras.splice(targetIndex, 0, movedItem);
      this._hasUnsavedOrder = true;
      this.render();
    }
    this._draggedIndex = null;
  }

  _handleDragEnd(e) {
    e.target.classList.remove("dragging");
    const cards = this.shadowRoot.querySelectorAll(".camera-card");
    cards.forEach((c) => c.classList.remove("drag-over"));
  }

  async _saveLayoutOrder() {
    if (!this._hass) return;
    const order = this._cameras.map((c) => c.id);
    try {
      await this._hass.callWS({
        type: "domolink_camera/save_layout",
        order: order,
      });
      this._hasUnsavedOrder = false;
      this._showToast("Disposition des caméras sauvegardée avec succès !");
      this.render();
    } catch (e) {
      console.error("Save layout failed", e);
      this._showToast("Erreur lors de la sauvegarde de l'ordre");
    }
  }

  // --- Live Stream Toggle ---
  _toggleLive(camId) {
    if (this._liveCameras.has(camId)) {
      this._liveCameras.delete(camId);
      this._hass.callWS({ type: "domolink_camera/trigger_live", camera_id: camId, live: false });
    } else {
      this._liveCameras.add(camId);
      this._hass.callWS({ type: "domolink_camera/trigger_live", camera_id: camId, live: true });
    }
    this.render();
  }

  // --- Toggle HA Entity from Card Banner ---
  async _toggleEntity(entityId) {
    if (!this._hass) return;
    const domain = entityId.split(".")[0];
    try {
      if (domain === "switch" || domain === "light" || domain === "fan") {
        await this._hass.callService("homeassistant", "toggle", { entity_id: entityId });
      } else if (domain === "lock") {
        const cur = this._hass.states[entityId]?.state;
        const svc = cur === "locked" ? "unlock" : "lock";
        await this._hass.callService("lock", svc, { entity_id: entityId });
      } else {
        this._showToast(`Entité ${entityId} : ${this._hass.states[entityId]?.state || "N/A"}`);
      }
    } catch (e) {
      console.error("Failed to toggle entity", e);
    }
  }

  // --- Settings Actions ---
  _appendLog(msg) {
    const time = new Date().toLocaleTimeString("fr-FR", { hour12: false });
    const formatted = `[${time}] ${msg}`;
    if (!this._pairingLogs) this._pairingLogs = [];
    this._pairingLogs.push(formatted);
    if (this._pairingLogs.length > 80) this._pairingLogs.shift();
    this._updatePairingLogs();
  }

  _updatePairingLogs() {
    const logBox = this.shadowRoot.querySelector("#pairing-logs") || this.shadowRoot.querySelector(".pairing-logs");
    if (logBox) {
      logBox.innerHTML = this._pairingLogs.map((l) => `<div>> ${l}</div>`).join("");
      logBox.scrollTop = logBox.scrollHeight;
    }
  }

  _triggerBrowserSideApPairing(apIp, ssid, pass) {
    const targets = [apIp, "192.168.1.1", "192.168.10.1", "192.168.1.254"].filter(Boolean);
    const uniqueTargets = Array.from(new Set(targets));
    const qSsid = encodeURIComponent(ssid);
    const qPass = encodeURIComponent(pass);

    // 1. Multi-path HTTP CGI injection (standard on YsxLite / A9 / HiSilicon / BK chips)
    uniqueTargets.forEach((ip) => {
      const urls = [
        `http://${ip}/set_wifi.cgi?ssid=${qSsid}&pwd=${qPass}`,
        `http://${ip}/wifi_set?ssid=${qSsid}&password=${qPass}`,
        `http://${ip}/cgi-bin/hi3510/param.cgi?cmd=setwirelessattr&-wf_ssid=${qSsid}&-wf_key=${qPass}`,
        `http://${ip}/config?ssid=${qSsid}&pwd=${qPass}`,
        `http://${ip}:8080/wifi_set?ssid=${qSsid}&password=${qPass}`,
      ];
      urls.forEach((u) => {
        try {
          const ctl = new AbortController();
          setTimeout(() => ctl.abort(), 2000);
          fetch(u, { mode: "no-cors", cache: "no-store", signal: ctl.signal }).catch(() => {});
          const img = new Image();
          img.src = u;
        } catch (e) {}
      });
    });

    // 2. WebRTC STUN datagram trigger on port 32108 (browser UDP packet dispatch)
    try {
      const rtcCls = window.RTCPeerConnection || window.webkitRTCPeerConnection;
      if (rtcCls) {
        const iceServers = uniqueTargets.map((ip) => ({ urls: `stun:${ip}:32108` }));
        const pc = new rtcCls({ iceServers: iceServers });
        pc.createDataChannel("domolink_probe");
        pc.createOffer()
          .then((offer) => pc.setLocalDescription(offer))
          .catch(() => {});
        setTimeout(() => {
          try {
            pc.close();
          } catch (e) {}
        }, 3000);
      }
    } catch (e) {}
  }

  async _startPairing() {
    const ssidInput = this.shadowRoot.querySelector("#pair-ssid");
    const passInput = this.shadowRoot.querySelector("#pair-pass");
    const apIpInput = this.shadowRoot.querySelector("#pair-ap-ip");

    const ssid = (ssidInput ? ssidInput.value : this._pairSsid || "").trim();
    const pass = passInput ? passInput.value : this._pairPass || "";
    const apIp = (apIpInput ? apIpInput.value : this._pairApIp || "192.168.1.1").trim() || "192.168.1.1";

    this._pairSsid = ssid;
    this._pairPass = pass;
    this._pairApIp = apIp;
    try {
      localStorage.setItem("domolink_pair_ssid", ssid);
      localStorage.setItem("domolink_pair_pass", pass);
      localStorage.setItem("domolink_pair_ap_ip", apIp);
    } catch (e) {}

    if (!ssid) {
      this._showToast("Veuillez saisir le SSID de votre réseau Wi-Fi.");
      this._appendLog("⚠️ [VALIDATION] Nom du réseau Wi-Fi (SSID) manquant.");
      return;
    }

    this._pairingActive = true;
    this._pairingLogs = [];
    this._appendLog(`🚀 [DÉMARRAGE] Assistant d'appairage lancé pour le réseau '${ssid}'...`);
    this._appendLog(`📋 [VÉRIFICATION] Longueur SSID=${ssid.length} car. | Longueur clé=${pass.length} car. | IP cible AP=${apIp}`);

    if (apIp === "192.168.1.254" || apIp === "192.168.0.254") {
      this._appendLog(`⚠️ [ATTENTION] L'adresse '${apIp}' est l'adresse de votre passerelle Freebox !`);
      this._appendLog("💡 L'adresse par défaut du point d'accès de votre caméra est généralement 192.168.1.1 ou 192.168.10.1.");
    }

    if (this._selectedCameraAp) {
      this._appendLog(`🎯 [PONT CAMÉRA] Point d'accès cible : '${this._selectedCameraAp}'`);
    }

    this.render();

    // Trigger immediate browser-side multi-vector injection (CGI + WebRTC UDP)
    this._appendLog(`📡 [INJECTION DIRECTE] Émission des trames Wi-Fi depuis le navigateur vers ${apIp}:32108 & HTTP CGI...`);
    this._triggerBrowserSideApPairing(apIp, ssid, pass);

    // Arm Home Assistant backend if connected
    try {
      await this._hass.callWS({
        type: "domolink_camera/start_pairing",
        ssid: ssid,
        password: pass,
        camera_ap_ip: apIp,
        camera_ssid: this._selectedCameraAp || undefined,
      });
      this._appendLog("✅ [SERVEUR ARMÉ] Home Assistant est en écoute active et scanne le réseau local (72s).");
    } catch (e) {
      const errMsg = e?.message || (typeof e === "object" ? JSON.stringify(e) : String(e));
      // If HA is currently disconnected (e.g. user already joined camera AP), do not crash!
      this._appendLog(`ℹ️ [LIAISON POINT D'ACCÈS] Connexion directe au point d'accès caméra : ${errMsg}`);
      this._appendLog("   Les trames Wi-Fi sont transmises en direct vers la caméra.");
      this._appendLog("💡 Reconnectez maintenant votre Mac/téléphone à votre Wi-Fi Freebox ('" + ssid + "').");
    }

    this._startResilientPairingPoll(ssid, pass, apIp);
  }

  _startResilientPairingPoll(ssid, pass, apIp) {
    if (this._pollTimer) clearInterval(this._pollTimer);
    let offlineCount = 0;
    let attempts = 0;
    const maxAttempts = 36; // 36 * 2s = 72s

    this._pollTimer = setInterval(async () => {
      attempts++;
      if (attempts > maxAttempts || !this._pairingActive) {
        clearInterval(this._pollTimer);
        this._pollTimer = null;
        this._pairingActive = false;
        this._appendLog("⚠️ [FIN DE TENTATIVE] Délai d'attente atteint (72s).");
        this._appendLog("💡 Cliquez sur 'Scanner le réseau' une fois votre appareil reconnecté à la Freebox.");
        this.render();
        return;
      }

      try {
        const st = await this._hass.callWS({ type: "domolink_camera/pair_status" });
        if (offlineCount > 0) {
          this._appendLog("🟢 [RECONNEXION HOME ASSISTANT] Liaison rétablie avec le serveur !");
          offlineCount = 0;
        }
        if (st) {
          if (st.logs && st.logs.length > 0) {
            this._pairingLogs = st.logs;
          }
          if (!st.active) {
            clearInterval(this._pollTimer);
            this._pollTimer = null;
            this._pairingActive = false;
            if (st.discovered && st.discovered.length > 0) {
              this._scanResults = st.discovered;
              this._scanCompatible = st.discovered;
              this._appendLog(`🎉 [SUCCÈS] Caméra découverte et appairée avec succès : ${st.discovered[0].name} (${st.discovered[0].host}) !`);
              this._showToast("Caméra appairée avec succès !");
            } else {
              this._appendLog("ℹ️ Écoute terminée. Lancement de la détection sur le réseau local...");
              this._scanLocalNetwork();
            }
            this.render();
          } else {
            this._updatePairingLogs();
          }
        }
      } catch (err) {
        offlineCount++;
        // Caught disconnection while user is on camera AP
        if (offlineCount === 1) {
          this._appendLog("📶 [BASCULE WI-FI DÉTECTÉE] Connecté au point d'accès de la caméra.");
          this._appendLog("📡 Envoi continu des identifiants Wi-Fi...");
        }
        if (offlineCount % 2 === 0) {
          this._triggerBrowserSideApPairing(apIp, ssid, pass);
        }
        this._updatePairingLogs();
      }
    }, 2000);
  }

  async _stopPairing() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
    this._pairingActive = false;
    try {
      await this._hass.callWS({ type: "domolink_camera/stop_pairing" });
    } catch (e) {}
    this._appendLog("🛑 [ARRÊT] Assistant d'appairage annulé.");
    this._showToast("Appairage annulé");
    this.render();
  }

  async _scanCameraAps() {
    this._appendLog("📡 [SCAN WI-FI AP] Recherche des caméras à proximité (Supervisor wlan0, nmcli & airport)...");
    try {
      const resp = await this._hass.callWS({ type: "domolink_camera/scan_wifi_aps" });
      if (resp && resp.aps) {
        this._detectedAps = resp.aps;
        const cams = resp.aps.filter((a) => a.is_camera);
        if (cams.length > 0) {
          this._appendLog(`🎯 [DÉTECTION] ${cams.length} caméra(s) identifiée(s) par motif ou UID :`);
          cams.forEach((c) => {
            this._appendLog(`   • SSID: ${c.ssid} (Signal: ${c.signal}%)`);
          });
          this._showToast(`${cams.length} caméra(s) Wi-Fi détectée(s) !`);
          // Auto-select first camera AP if none selected
          if (!this._selectedCameraAp && cams.length > 0) {
            this._selectedCameraAp = cams[0].ssid;
            this._pairApIp = "192.168.1.1";
          }
        } else {
          this._appendLog(`ℹ️ [INFO] Aucun SSID de caméra identifié parmi les ${resp.aps.length} réseaux scannés.`);
        }
        this.render();
      }
    } catch (err) {
      const errMsg = err?.message || (typeof err === "object" ? JSON.stringify(err) : String(err));
      this._appendLog(`⚠️ Analyse Wi-Fi non disponible sur l'hôte : ${errMsg}`);
    }
  }

  async _scanLocalNetwork() {
    this._isScanning = true;
    this._appendLog("🔍 [SCAN RÉSEAU] Démarrage du scan multi-sources (Local LAN & Entités HA)...");
    this._appendLog("📡 [LAN] Envoi broadcast UDP sur le port 32108 pour détecter caméras PPPP / YsxLite...");
    this._appendLog("🌐 [LAN] Analyse de la table ARP et test de réponse RTSP port 554...");
    this._appendLog("🏠 [HA] Inspection des comptes et entités caméras enregistrées dans Home Assistant...");
    this._showToast("Scan du réseau en cours (UDP 32108, RTSP 554 & Entités HA)...");
    this.render();

    try {
      const resp = await this._hass.callWS({ type: "domolink_camera/scan_local" });
      this._isScanning = false;
      if (resp) {
        this._scanCompatible = resp.compatible || [];
        this._scanIncompatible = resp.incompatible || [];
        this._scanSummary = resp.summary || {
          total: this._scanCompatible.length + this._scanIncompatible.length,
          compatible_count: this._scanCompatible.length,
          incompatible_count: this._scanIncompatible.length,
        };
        this._scanResults = this._scanCompatible;

        this._appendLog(`✅ [SCAN TERMINÉ] ${this._scanCompatible.length} caméra(s) compatible(s) trouvée(s) et prête(s) à l'ajout !`);
        if (this._scanIncompatible.length > 0) {
          this._appendLog(`ℹ️ [INFO] ${this._scanIncompatible.length} entité(s) secondaire(s) ou distantes filtrées.`);
        }

        this._showToast(
          `Scan terminé : ${this._scanCompatible.length} caméra(s) prête(s) à l'intégration !`
        );
        this.render();
      }
    } catch (e) {
      this._isScanning = false;
      this._appendLog(`❌ [ERREUR SCAN] Échec de l'analyse : ${e.message || e}`);
      this._showToast("Erreur lors du scan du réseau");
      this.render();
    }
  }

  async _addDiscoveredCamera(dev) {
    this._appendLog(`📥 [INTÉGRATION] Ajout de la caméra '${dev.name}' en cours...`);
    this._appendLog(`⚙️ [CONFIGURATION] Pilote assigné : ${dev.driver} (Cible : ${dev.host})`);

    const newCam = {
      name: dev.name || dev.model || "Caméra Wi-Fi",
      description: dev.details || "Caméra intégrée",
      driver: dev.driver || "ha_proxy",
      host: dev.host,
      port: dev.port || (dev.driver === "generic_rtsp" ? 554 : 32108),
      linked_entities: [],
    };

    try {
      this._appendLog("📸 [TEST FLUX] Vérification de l'acquisition de snapshot et initialisation du pilote...");
      await this._saveCamera(newCam);

      dev.already_added = true;
      this._appendLog(`✅ [SUCCÈS] Caméra '${dev.name}' ajoutée à DomoLink ! Retrouvez-la dans l'onglet Caméras.`);
      this._showToast(`Caméra ${dev.name} ajoutée avec succès !`);
      await this._fetchCameras();
      this.render();
    } catch (err) {
      this._appendLog(`❌ [ERREUR INTÉGRATION] Impossible d'ajouter '${dev.name}' : ${err.message || err}`);
      this._showToast(`Erreur lors de l'ajout : ${err.message || err}`);
    }
  }

  async _saveCamera(cam) {
    try {
      await this._hass.callWS({
        type: "domolink_camera/save_camera",
        camera: cam,
      });
      this._showToast("Caméra enregistrée !");
      await this._fetchCameras();
      this._selectedCamera = null;
      this.render();
    } catch (e) {
      this._showToast("Erreur d'enregistrement de la caméra");
    }
  }

  async _deleteCamera(camId) {
    if (!confirm("Voulez-vous vraiment supprimer cette caméra ?")) return;
    try {
      await this._hass.callWS({
        type: "domolink_camera/delete_camera",
        camera_id: camId,
      });
      this._showToast("Caméra supprimée.");
      await this._fetchCameras();
      this.render();
    } catch (e) {
      this._showToast("Erreur lors de la suppression");
    }
  }

  _formatTime(timestamp) {
    if (!timestamp) return "Pas de snapshot";
    const d = new Date(timestamp * 1000);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  _getEntityIcon(domain) {
    switch (domain) {
      case "light":
        return "💡";
      case "switch":
        return "🔌";
      case "binary_sensor":
        return "🚨";
      case "sensor":
        return "🌡️";
      case "lock":
        return "🔒";
      case "cover":
        return "🪟";
      case "climate":
        return "❄️";
      default:
        return "⚡";
    }
  }

  render() {
    try {
      this._renderInner();
    } catch (err) {
      console.error("[DomoLink-Camera] Render error:", err);
      if (this.shadowRoot) {
        this.shadowRoot.innerHTML = `
          <div style="padding: 40px; color: #ef4444; font-family: sans-serif; background: #0d1117; min-height: 100vh;">
            <h2>⚠️ Erreur d'affichage DomoLink Camera</h2>
            <pre style="background: rgba(0,0,0,0.5); padding: 16px; border-radius: 8px; color: #f87171; white-space: pre-wrap;">${err.stack || err.message || err}</pre>
            <button id="btn-reload-panel" style="background: #3b82f6; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; margin-top: 16px;">Réessayer</button>
          </div>
        `;
        const rBtn = this.shadowRoot.querySelector("#btn-reload-panel");
        if (rBtn) rBtn.onclick = () => this.render();
      }
    }
  }

  _renderInner() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100vh;
          box-sizing: border-box;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
          background: #0d1117;
          color: #f0f6fc;
          margin: 0;
          padding: 24px;
        }

        /* ─── Domolink Glassmorphism Theme ─── */
        .panel-container {
          max-width: 1500px;
          margin: 0 auto;
        }

        header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding-bottom: 20px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          margin-bottom: 24px;
        }

        .brand-box {
          display: flex;
          align-items: center;
          gap: 14px;
        }

        .brand-icon {
          width: 44px;
          height: 44px;
          background: linear-gradient(135deg, #2563eb, #3b82f6);
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 24px;
          box-shadow: 0 4px 16px rgba(37, 99, 235, 0.35);
        }

        .brand-title {
          font-size: 22px;
          font-weight: 700;
          letter-spacing: -0.5px;
          background: linear-gradient(90deg, #f0f6fc, #93c5fd);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        .brand-subtitle {
          font-size: 13px;
          color: #8b949e;
        }

        /* Tabs */
        .tabs {
          display: flex;
          background: rgba(22, 27, 34, 0.85);
          padding: 4px;
          border-radius: 10px;
          border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .tab-btn {
          background: transparent;
          border: none;
          color: #8b949e;
          padding: 8px 18px;
          font-size: 14px;
          font-weight: 600;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s ease;
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .tab-btn.active {
          background: #3b82f6;
          color: #ffffff;
          box-shadow: 0 2px 8px rgba(59, 130, 246, 0.4);
        }

        .tab-btn:hover:not(.active) {
          color: #f0f6fc;
        }

        /* Unsaved Order Floating Bar */
        .save-order-bar {
          position: fixed;
          bottom: 24px;
          left: 50%;
          transform: translateX(-50%);
          background: rgba(37, 99, 235, 0.95);
          backdrop-filter: blur(12px);
          color: #fff;
          padding: 12px 24px;
          border-radius: 50px;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(59, 130, 246, 0.5);
          display: flex;
          align-items: center;
          gap: 16px;
          z-index: 1000;
          animation: popUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }

        @keyframes popUp {
          from { opacity: 0; transform: translate(-50%, 20px); }
          to { opacity: 1; transform: translate(-50%, 0); }
        }

        .save-btn {
          background: #ffffff;
          color: #1e3a8a;
          border: none;
          padding: 8px 18px;
          border-radius: 20px;
          font-weight: 700;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .save-btn:hover {
          background: #eff6ff;
          transform: scale(1.05);
        }

        /* Grid */
        .camera-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
          gap: 24px;
        }

        /* Camera Card */
        .camera-card {
          background: rgba(22, 27, 34, 0.85);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
          backdrop-filter: blur(20px);
          transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
          position: relative;
          cursor: grab;
        }

        .camera-card:hover {
          border-color: rgba(59, 130, 246, 0.4);
          box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5), 0 0 16px rgba(59, 130, 246, 0.15);
        }

        .camera-card.dragging {
          opacity: 0.4;
          transform: scale(0.98);
        }

        .camera-card.drag-over {
          border: 2px dashed #3b82f6;
          transform: scale(1.02);
        }

        /* Card Header */
        .card-header {
          padding: 12px 16px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          background: rgba(13, 17, 23, 0.6);
        }

        .card-title-box {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #8b949e;
        }

        .status-dot.online { background: #10b981; box-shadow: 0 0 8px #10b981; }
        .status-dot.streaming { background: #ef4444; box-shadow: 0 0 8px #ef4444; animation: blink 1s infinite; }
        .status-dot.offline { background: #64748b; }

        @keyframes blink {
          50% { opacity: 0.4; }
        }

        .card-name {
          font-weight: 600;
          font-size: 15px;
        }

        .driver-badge {
          font-size: 10px;
          background: rgba(255, 255, 255, 0.08);
          color: #93c5fd;
          padding: 2px 6px;
          border-radius: 4px;
          text-transform: uppercase;
        }

        /* Viewport / Video Area */
        .viewport {
          position: relative;
          width: 100%;
          aspect-ratio: 16 / 9;
          background: #000;
          overflow: hidden;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .viewport img {
          width: 100%;
          height: 100%;
          object-fit: cover;
          display: block;
        }

        /* Rollover Tooltip */
        .rollover-tooltip {
          position: absolute;
          top: 10px;
          left: 10px;
          right: 10px;
          background: rgba(13, 17, 23, 0.92);
          backdrop-filter: blur(10px);
          border: 1px solid rgba(255, 255, 255, 0.15);
          padding: 8px 12px;
          border-radius: 8px;
          font-size: 12px;
          color: #f0f6fc;
          opacity: 0;
          transform: translateY(-6px);
          pointer-events: none;
          transition: all 0.2s ease;
          z-index: 10;
          line-height: 1.4;
          box-shadow: 0 4px 16px rgba(0,0,0,0.4);
        }

        .viewport:hover .rollover-tooltip {
          opacity: 1;
          transform: translateY(0);
        }

        /* Live Button on Viewport */
        .live-btn {
          position: absolute;
          bottom: 10px;
          right: 10px;
          background: rgba(22, 27, 34, 0.85);
          backdrop-filter: blur(8px);
          border: 1px solid rgba(255, 255, 255, 0.2);
          color: #f0f6fc;
          padding: 6px 12px;
          border-radius: 6px;
          font-size: 11px;
          font-weight: 700;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 6px;
          transition: all 0.15s ease;
          z-index: 5;
        }

        .live-btn:hover {
          background: #2563eb;
          border-color: #60a5fa;
        }

        .live-btn.active {
          background: #ef4444;
          border-color: #f87171;
          color: white;
          animation: pulseRed 2s infinite;
        }

        @keyframes pulseRed {
          0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.6); }
          50% { box-shadow: 0 0 0 6px rgba(239, 68, 68, 0); }
        }

        .time-badge {
          position: absolute;
          bottom: 10px;
          left: 10px;
          background: rgba(0, 0, 0, 0.65);
          color: #94a3b8;
          font-size: 10px;
          padding: 3px 6px;
          border-radius: 4px;
        }

        /* Bottom Interactive Banner (Linked Entities) */
        .bottom-banner {
          background: rgba(15, 23, 42, 0.7);
          border-top: 1px solid rgba(255, 255, 255, 0.05);
          padding: 8px 12px;
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          align-items: center;
          min-height: 38px;
        }

        .banner-empty-msg {
          font-size: 11px;
          color: #64748b;
          font-style: italic;
        }

        .entity-badge {
          background: rgba(255, 255, 255, 0.06);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 6px;
          padding: 4px 8px;
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 11px;
          color: #cbd5e1;
          cursor: pointer;
          transition: all 0.15s ease;
          user-select: none;
        }

        .entity-badge:hover {
          background: rgba(59, 130, 246, 0.2);
          border-color: #3b82f6;
          color: #ffffff;
        }

        .entity-badge.active {
          background: rgba(16, 185, 129, 0.2);
          border-color: #10b981;
          color: #a7f3d0;
        }

        .badge-icon { font-size: 13px; }
        .badge-name { font-weight: 500; }
        .badge-state { font-weight: 600; opacity: 0.9; }

        /* Settings View */
        .settings-container {
          display: flex;
          flex-direction: column;
          gap: 24px;
        }

        .settings-card {
          background: rgba(22, 27, 34, 0.85);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          padding: 24px;
          backdrop-filter: blur(20px);
          box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }

        .settings-card h3 {
          margin-top: 0;
          font-size: 18px;
          display: flex;
          align-items: center;
          gap: 10px;
          color: #f0f6fc;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          padding-bottom: 12px;
        }

        .form-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
          gap: 16px;
          margin-top: 16px;
        }

        .form-group {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .form-group label {
          font-size: 12px;
          font-weight: 600;
          color: #8b949e;
        }

        .form-input, .form-select {
          background: rgba(13, 17, 23, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.15);
          border-radius: 8px;
          padding: 10px 12px;
          color: #f0f6fc;
          font-size: 14px;
          outline: none;
          transition: border-color 0.15s ease;
        }

        .form-input:focus, .form-select:focus {
          border-color: #3b82f6;
          box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
        }

        .btn-primary {
          background: #2563eb;
          color: white;
          border: none;
          padding: 10px 18px;
          border-radius: 8px;
          font-weight: 600;
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          transition: background 0.15s ease;
        }

        .btn-primary:hover { background: #1d4ed8; }

        .btn-secondary {
          background: rgba(255, 255, 255, 0.08);
          color: #f0f6fc;
          border: 1px solid rgba(255, 255, 255, 0.15);
          padding: 8px 14px;
          border-radius: 8px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .btn-secondary:hover {
          background: rgba(255, 255, 255, 0.14);
        }

        .btn-danger {
          background: rgba(239, 68, 68, 0.2);
          color: #f87171;
          border: 1px solid rgba(239, 68, 68, 0.4);
          padding: 8px 14px;
          border-radius: 8px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .btn-danger:hover {
          background: #ef4444;
          color: white;
        }

        /* Pairing Logs Terminal Card */
        .terminal-card {
          margin-top: 18px;
          background: #060a12;
          border: 1px solid rgba(74, 222, 128, 0.3);
          border-radius: 12px;
          overflow: hidden;
          box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5);
        }

        .terminal-header {
          background: rgba(15, 23, 42, 0.95);
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          padding: 10px 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .terminal-dots {
          display: flex;
          gap: 6px;
        }

        .terminal-dots span {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          display: inline-block;
        }

        .dot-red { background: #ef4444; }
        .dot-yellow { background: #f59e0b; }
        .dot-green { background: #10b981; }

        .terminal-title {
          font-size: 12px;
          font-family: 'SF Mono', Monaco, Consolas, monospace;
          color: #94a3b8;
          font-weight: 600;
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .terminal-status-badge {
          background: rgba(16, 185, 129, 0.2);
          color: #34d399;
          font-size: 10px;
          padding: 2px 6px;
          border-radius: 4px;
        }

        .btn-clear-terminal {
          background: transparent;
          border: 1px solid rgba(255, 255, 255, 0.15);
          color: #94a3b8;
          font-size: 11px;
          padding: 3px 10px;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .btn-clear-terminal:hover {
          color: #ffffff;
          border-color: #3b82f6;
          background: rgba(59, 130, 246, 0.15);
        }

        .pairing-logs {
          background: #040810;
          padding: 14px 16px;
          font-family: 'SF Mono', Monaco, Consolas, monospace;
          font-size: 12px;
          line-height: 1.6;
          color: #4ade80;
          min-height: 120px;
          max-height: 240px;
          overflow-y: auto;
          white-space: pre-wrap;
          word-break: break-word;
        }

        /* Discovered List & Categorized Scan */
        .scan-summary-bar {
          display: flex;
          gap: 12px;
          margin-top: 16px;
          flex-wrap: wrap;
        }

        .summary-chip {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 8px 14px;
          border-radius: 20px;
          font-size: 13px;
          font-weight: 600;
        }

        .summary-chip.chip-compatible {
          background: rgba(16, 185, 129, 0.15);
          color: #34d399;
          border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .summary-chip.chip-incompatible {
          background: rgba(245, 158, 11, 0.15);
          color: #fbbf24;
          border: 1px solid rgba(245, 158, 11, 0.3);
        }

        .scan-category-section {
          margin-top: 20px;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .scan-category-header {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
          font-weight: 600;
          padding-bottom: 6px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }

        .discovered-list {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .discovered-item {
          background: rgba(13, 17, 23, 0.7);
          border-radius: 10px;
          padding: 14px 16px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 16px;
          transition: transform 0.15s, border-color 0.15s;
        }

        .discovered-item.compatible {
          border: 1px solid rgba(16, 185, 129, 0.35);
        }

        .discovered-item.compatible:hover {
          border-color: rgba(16, 185, 129, 0.6);
          transform: translateY(-1px);
        }

        .discovered-item.incompatible {
          border: 1px solid rgba(245, 158, 11, 0.3);
          background: rgba(24, 20, 16, 0.6);
        }

        .badge-protocol {
          display: inline-block;
          font-size: 11px;
          font-weight: 600;
          padding: 2px 8px;
          border-radius: 6px;
          margin-right: 6px;
          text-transform: uppercase;
          letter-spacing: 0.3px;
        }

        .badge-protocol.badge-green {
          background: rgba(16, 185, 129, 0.2);
          color: #34d399;
          border: 1px solid rgba(16, 185, 129, 0.4);
        }

        .badge-protocol.badge-orange {
          background: rgba(245, 158, 11, 0.2);
          color: #fbbf24;
          border: 1px solid rgba(245, 158, 11, 0.4);
        }

        .badge-protocol.badge-gray {
          background: rgba(148, 163, 184, 0.15);
          color: #94a3b8;
          border: 1px solid rgba(148, 163, 184, 0.3);
        }

        .badge-already-added {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          font-size: 12px;
          font-weight: 600;
          color: #34d399;
          background: rgba(16, 185, 129, 0.15);
          padding: 6px 12px;
          border-radius: 6px;
          border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .reason-box {
          margin-top: 6px;
          padding: 8px 12px;
          background: rgba(245, 158, 11, 0.08);
          border-left: 3px solid #f59e0b;
          border-radius: 0 6px 6px 0;
          font-size: 12px;
          color: #e2e8f0;
          line-height: 1.4;
        }

        /* Toast */
        .toast-bar {
          position: fixed;
          top: 20px;
          right: 20px;
          background: #1e293b;
          border: 1px solid #3b82f6;
          color: #f0f6fc;
          padding: 12px 20px;
          border-radius: 10px;
          box-shadow: 0 8px 24px rgba(0,0,0,0.4);
          font-size: 14px;
          font-weight: 500;
          opacity: 0;
          transform: translateY(-10px);
          pointer-events: none;
          transition: all 0.25s ease;
          z-index: 2000;
        }

        .toast-bar.show {
          opacity: 1;
          transform: translateY(0);
        }

        /* Camera Edit List */
        .camera-edit-table {
          width: 100%;
          border-collapse: collapse;
          margin-top: 16px;
        }

        .camera-edit-table th, .camera-edit-table td {
          padding: 12px;
          text-align: left;
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }

        .camera-edit-table th {
          color: #8b949e;
          font-size: 12px;
        }

        /* TV Section Styles */
        .tv-container {
          display: flex;
          flex-direction: column;
          gap: 24px;
        }

        .box-info-card {
          background: rgba(22, 27, 34, 0.85);
          border: 1px solid rgba(59, 130, 246, 0.3);
          border-radius: 16px;
          padding: 18px 24px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
          backdrop-filter: blur(20px);
        }

        .box-info-left {
          display: flex;
          align-items: center;
          gap: 16px;
        }

        .box-icon {
          font-size: 32px;
          background: rgba(59, 130, 246, 0.15);
          width: 56px;
          height: 56px;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 14px;
          border: 1px solid rgba(59, 130, 246, 0.3);
        }

        .box-title {
          font-size: 17px;
          font-weight: 700;
          color: #f0f6fc;
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .box-badge {
          background: #10b981;
          color: #064e3b;
          font-size: 11px;
          font-weight: 700;
          padding: 3px 9px;
          border-radius: 12px;
        }

        .box-desc {
          font-size: 13px;
          color: #8b949e;
          margin-top: 4px;
        }

        .tv-player-card {
          background: rgba(22, 27, 34, 0.85);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          overflow: hidden;
          box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
          backdrop-filter: blur(20px);
        }

        .tv-player-header {
          padding: 14px 20px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: rgba(13, 17, 23, 0.8);
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }

        .tv-channel-title {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .tv-ch-num {
          background: #3b82f6;
          color: #ffffff;
          font-weight: 800;
          font-size: 13px;
          padding: 2px 8px;
          border-radius: 6px;
        }

        .tv-ch-name {
          font-size: 18px;
          font-weight: 700;
          color: #ffffff;
        }

        .tv-live-tag {
          background: rgba(239, 68, 68, 0.2);
          color: #ef4444;
          border: 1px solid rgba(239, 68, 68, 0.4);
          font-size: 11px;
          font-weight: 700;
          padding: 3px 8px;
          border-radius: 6px;
          display: flex;
          align-items: center;
          gap: 5px;
        }

        .tv-header-actions {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .btn-tv-action {
          background: rgba(255, 255, 255, 0.08);
          color: #f0f6fc;
          border: 1px solid rgba(255, 255, 255, 0.15);
          padding: 7px 14px;
          border-radius: 8px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 6px;
          transition: all 0.2s ease;
        }

        .btn-tv-action:hover {
          background: rgba(59, 130, 246, 0.2);
          border-color: #3b82f6;
          color: #60a5fa;
        }

        .btn-tv-action.primary {
          background: #3b82f6;
          color: #ffffff;
          border: none;
        }

        .btn-tv-action.primary:hover {
          background: #2563eb;
        }

        .tv-player-wrapper {
          position: relative;
          background: #000000;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 100%;
          min-height: 380px;
          max-height: 560px;
        }

        .tv-player-wrapper video {
          width: 100%;
          height: auto;
          max-height: 560px;
          display: block;
        }

        /* Fullscreen handling */
        .tv-player-wrapper:fullscreen {
          width: 100vw;
          height: 100vh;
          max-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          background: #000000;
        }

        .tv-player-wrapper:fullscreen video {
          max-height: 100vh;
          width: 100%;
          height: 100%;
          object-fit: contain;
        }

        /* TV Channel Selector */
        .tv-selector-card {
          background: rgba(22, 27, 34, 0.85);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          padding: 24px;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
          backdrop-filter: blur(20px);
        }

        .tv-selector-header {
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          gap: 16px;
          margin-bottom: 20px;
        }

        .tv-search-box {
          position: relative;
          min-width: 280px;
          flex: 1;
          max-width: 400px;
        }

        .tv-search-input {
          width: 100%;
          padding: 10px 14px 10px 38px;
          background: rgba(13, 17, 23, 0.7);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 10px;
          color: #f0f6fc;
          font-size: 14px;
          outline: none;
          box-sizing: border-box;
          transition: border-color 0.2s ease;
        }

        .tv-search-input:focus {
          border-color: #3b82f6;
        }

        .tv-search-icon {
          position: absolute;
          left: 12px;
          top: 50%;
          transform: translateY(-50%);
          font-size: 14px;
          color: #8b949e;
        }

        .category-pills {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .category-pill {
          background: rgba(255, 255, 255, 0.05);
          color: #8b949e;
          border: 1px solid rgba(255, 255, 255, 0.08);
          padding: 6px 14px;
          border-radius: 20px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .category-pill:hover {
          background: rgba(255, 255, 255, 0.1);
          color: #f0f6fc;
        }

        .category-pill.active {
          background: #3b82f6;
          color: #ffffff;
          border-color: #3b82f6;
        }

        .channel-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 16px;
          max-height: 480px;
          overflow-y: auto;
          padding-right: 6px;
        }

        .channel-card {
          background: rgba(13, 17, 23, 0.6);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          padding: 14px;
          display: flex;
          align-items: center;
          gap: 12px;
          cursor: pointer;
          transition: all 0.2s ease;
          position: relative;
        }

        .channel-card:hover {
          background: rgba(59, 130, 246, 0.1);
          border-color: rgba(59, 130, 246, 0.4);
          transform: translateY(-2px);
        }

        .channel-card.active {
          background: rgba(59, 130, 246, 0.2);
          border-color: #3b82f6;
          box-shadow: 0 0 16px rgba(59, 130, 246, 0.3);
        }

        .channel-logo-box {
          width: 44px;
          height: 44px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
          flex-shrink: 0;
        }

        .channel-logo-img {
          max-width: 38px;
          max-height: 38px;
          object-fit: contain;
        }

        .channel-details {
          flex: 1;
          min-width: 0;
        }

        .channel-name {
          font-weight: 600;
          font-size: 14px;
          color: #f0f6fc;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .channel-sub {
          font-size: 11px;
          color: #8b949e;
          margin-top: 2px;
        }
      </style>

      <div class="panel-container">
        <!-- Toast Notification -->
        <div class="toast-bar"></div>

        <!-- Header -->
        <header>
          <div class="brand-box">
            <div class="brand-icon">📹</div>
            <div>
              <div class="brand-title">DomoLink-Camera</div>
              <div class="brand-subtitle">Gestion & Flux en direct pour caméras Wi-Fi</div>
            </div>
          </div>

          <div class="tabs">
            <button class="tab-btn ${this._activeTab === "cameras" ? "active" : ""}" id="tab-cameras">
              <span>🖼️</span> Caméras (${this._cameras.length})
            </button>
            <button class="tab-btn ${this._activeTab === "tv" ? "active" : ""}" id="tab-tv">
              <span>📺</span> TV en Direct
            </button>
            <button class="tab-btn ${this._activeTab === "settings" ? "active" : ""}" id="tab-settings">
              <span>⚙️</span> Paramètres & Appairage
            </button>
          </div>
        </header>

        <!-- Main Content Area -->
        ${
          this._activeTab === "cameras"
            ? this._renderCamerasGrid()
            : this._activeTab === "tv"
            ? this._renderTvSection()
            : this._renderSettings()
        }

        <!-- Save Layout Order Floating Bar -->
        ${
          this._hasUnsavedOrder && this._activeTab === "cameras"
            ? `
          <div class="save-order-bar">
            <span>✨ Disposition des vignettes modifiée</span>
            <button class="save-btn" id="btn-save-layout">💾 Sauvegarder l'ordre</button>
          </div>
        `
            : ""
        }
      </div>
    `;

    this._bindEvents();
  }

  _renderCamerasGrid() {
    if (!this._cameras || this._cameras.length === 0) {
      return `
        <div style="text-align: center; padding: 80px 20px; background: rgba(22,27,34,0.5); border-radius: 16px; border: 1px dashed rgba(255,255,255,0.1);">
          <div style="font-size: 48px; margin-bottom: 16px;">📹</div>
          <div style="font-size: 18px; font-weight: 600; margin-bottom: 8px;">Aucune caméra configurée</div>
          <div style="color: #8b949e; margin-bottom: 24px; max-width: 480px; margin-left: auto; margin-right: auto;">
            Ajoutez votre première caméra Wi-Fi (YsxLite, A9, RTSP, ONVIF) depuis l'onglet Paramètres sans aucune application mobile.
          </div>
          <button class="btn-primary" id="btn-goto-settings">Lancer l'appairage</button>
        </div>
      `;
    }

    return `
      <div class="camera-grid">
        ${this._cameras
          .map((cam, idx) => {
            const isLive = this._liveCameras.has(cam.id);
            const statusClass = cam.status || "offline";
            const stateObj = (cam.driver === "ha_proxy" && this._hass) ? this._hass.states[cam.host] : null;

            let snapUrl = `/api/domolink_camera/snapshot/${cam.id}?t=${cam.snapshot_timestamp || Date.now()}`;
            if (isLive) {
              if (cam.driver === "ha_proxy" && stateObj?.attributes?.access_token) {
                snapUrl = `/api/camera_proxy_stream/${cam.host}?token=${stateObj.attributes.access_token}`;
              } else {
                snapUrl = `/api/domolink_camera/stream/${cam.id}`;
              }
            } else if (cam.driver === "ha_proxy" && stateObj?.attributes?.entity_picture) {
              const pic = stateObj.attributes.entity_picture;
              snapUrl = pic.startsWith("http") ? pic : (this._hass.hassUrl ? this._hass.hassUrl(pic) : pic);
            }

            const driverLabel = cam.driver === "ysxlite_pppp" ? "YsxLite" : cam.driver === "ha_proxy" ? "Passerelle HA" : "RTSP";

            return `
            <div class="camera-card" 
                 draggable="true" 
                 data-id="${cam.id}" 
                 data-index="${idx}">
              
              <!-- Card Header -->
              <div class="card-header">
                <div class="card-title-box">
                  <div class="status-dot ${isLive ? "streaming" : statusClass}"></div>
                  <div class="card-name">${cam.name}</div>
                  <span class="driver-badge">${driverLabel}</span>
                </div>
                <div style="font-size: 12px; color: #8b949e; cursor: grab;" title="Glisser pour réorganiser">⠿</div>
              </div>

              <!-- Viewport with Image/Live Stream -->
              <div class="viewport">
                <img src="${snapUrl}" alt="${cam.name}" loading="lazy" />

                <!-- Rollover Hover Tooltip -->
                <div class="rollover-tooltip">
                  <strong>${cam.name}</strong> (${cam.host || "IP non assignée"})<br/>
                  ${cam.description ? cam.description : "<i>Aucune description renseignée.</i>"}
                </div>

                <!-- Live Button -->
                <button class="live-btn ${isLive ? "active" : ""}" data-cam-id="${cam.id}">
                  ${isLive ? "🔴 EN DIRECT" : "▶ LIVE"}
                </button>

                <!-- Snapshot Time badge -->
                <div class="time-badge">
                  ${isLive ? "Flux continu" : this._formatTime(cam.snapshot_timestamp)}
                </div>
              </div>

              <!-- Bottom Interactive Banner (Linked Entities) -->
              <div class="bottom-banner">
                ${
                  cam.linked_entities && cam.linked_entities.length > 0
                    ? cam.linked_entities
                        .map((entId) => {
                          const stateObj = this._hass ? this._hass.states[entId] : null;
                          const domain = entId.split(".")[0];
                          const icon = this._getEntityIcon(domain);
                          const friendly = stateObj ? stateObj.attributes.friendly_name || entId : entId;
                          const stateVal = stateObj ? stateObj.state : "N/A";
                          const unit = stateObj?.attributes.unit_of_measurement || "";
                          const isActive = stateVal === "on";

                          return `
                        <div class="entity-badge ${isActive ? "active" : ""}" data-entity-id="${entId}" title="${friendly} (${entId})">
                          <span class="badge-icon">${icon}</span>
                          <span class="badge-name">${friendly}</span>
                          <span class="badge-state">${stateVal} ${unit}</span>
                        </div>
                      `;
                        })
                        .join("")
                    : `<span class="banner-empty-msg">Aucune entité liée (ajoutez switchs/capteurs dans les réglages)</span>`
                }
              </div>

            </div>
          `;
          })
          .join("")}
      </div>
    `;
  }

  // --- TV Section & Player ---
  async _fetchTvData() {
    if (this._isLoadingTv) return;
    this._isLoadingTv = true;
    try {
      const resp = await this._hass.callWS({ type: "domolink_camera/get_tv_channels" });
      if (resp) {
        this._boxInfo = resp.box || null;
        this._tvChannels = resp.channels || [];
        if (!this._selectedChannel && this._tvChannels.length > 0) {
          this._selectedChannel = this._tvChannels[0];
        }
        this.render();
        if (this._selectedChannel) {
          this._playChannelStream(this._selectedChannel);
        }
      }
    } catch (err) {
      console.error("Error loading TV channels:", err);
      this._showToast("Erreur lors de la détection de la Box ou des flux TV");
    } finally {
      this._isLoadingTv = false;
    }
  }

  _ensureHlsJs() {
    if (window.Hls) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://cdn.jsdelivr.net/npm/hls.js@1.5.8/dist/hls.min.js";
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Impossible de charger le moteur HLS"));
      document.head.appendChild(script);
    });
  }

  async _playChannelStream(channel) {
    if (!channel) return;
    this._selectedChannel = channel;
    const video = this.shadowRoot.querySelector("#tv-video-player");
    if (!video) return;

    this._showToast(`Chargement du direct : ${channel.name}...`);
    try {
      const resp = await this._hass.callWS({
        type: "domolink_camera/get_tv_stream",
        channel_id: channel.id,
      });

      if (!resp || !resp.url) {
        this._showToast(`Flux indisponible pour ${channel.name}`);
        return;
      }

      const streamUrl = resp.url;
      const isHls = streamUrl.includes(".m3u8") || resp.format === "hls";

      if (isHls) {
        if (video.canPlayType("application/vnd.apple.mpegurl")) {
          video.src = streamUrl;
          video.play().catch(() => {});
        } else {
          await this._ensureHlsJs();
          if (window.Hls && window.Hls.isSupported()) {
            if (this._hlsPlayer) {
              this._hlsPlayer.destroy();
            }
            this._hlsPlayer = new window.Hls({
              enableWorker: true,
              lowLatencyMode: true,
            });
            this._hlsPlayer.loadSource(streamUrl);
            this._hlsPlayer.attachMedia(video);
            this._hlsPlayer.on(window.Hls.Events.MANIFEST_PARSED, () => {
              video.play().catch(() => {});
            });
          } else {
            video.src = streamUrl;
            video.play().catch(() => {});
          }
        }
      } else {
        video.src = streamUrl;
        video.play().catch(() => {});
      }
    } catch (err) {
      console.error("TV stream error:", err);
      this._showToast(`Erreur flux TV: ${err.message || err}`);
    }
  }

  _toggleFullscreen() {
    const wrapper = this.shadowRoot.querySelector("#tv-player-wrapper");
    if (!wrapper) return;

    if (!document.fullscreenElement && !document.webkitFullscreenElement) {
      if (wrapper.requestFullscreen) {
        wrapper.requestFullscreen();
      } else if (wrapper.webkitRequestFullscreen) {
        wrapper.webkitRequestFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      }
    }
  }

  async _togglePip() {
    const video = this.shadowRoot.querySelector("#tv-video-player");
    if (!video) return;
    try {
      if (document.pictureInPictureElement) {
        await document.exitPictureInPicture();
      } else if (video.requestPictureInPicture) {
        await video.requestPictureInPicture();
      }
    } catch (e) {
      console.warn("PiP error:", e);
    }
  }

  async _pinCurrentChannel() {
    if (!this._selectedChannel) return;
    try {
      const resp = await this._hass.callWS({
        type: "domolink_camera/pin_tv_camera",
        channel_id: this._selectedChannel.id,
      });
      if (resp && resp.success) {
        this._showToast(`Chaîne ${this._selectedChannel.name} ajoutée à vos caméras !`);
        await this._fetchCameras();
      }
    } catch (err) {
      this._showToast(`Erreur lors de l'épinglage: ${err.message || err}`);
    }
  }

  _renderTvSection() {
    if (!this._boxInfo && !this._isLoadingTv) {
      setTimeout(() => this._fetchTvData(), 10);
      return `
        <div style="text-align: center; padding: 60px 20px;">
          <div class="loading-spinner"></div>
          <div style="margin-top: 16px; color: #8b949e;">Détection de votre Box Internet et chargement des flux TV...</div>
        </div>
      `;
    }

    const box = this._boxInfo || {
      brand: "free",
      name: "Freebox Server",
      model: "Freebox Ultra",
      badge: "Multiposte Actif ⚡",
      description: "Accès direct aux flux vidéo Multiposte RTSP locaux en qualité maximale.",
    };

    const isFree = box.brand === "free";
    const boxIcon = isFree ? "⚡" : box.brand === "orange" ? "🍊" : box.brand === "sfr" ? "🔴" : box.brand === "bouygues" ? "🔷" : "🌐";

    const ch = this._selectedChannel || (this._tvChannels.length > 0 ? this._tvChannels[0] : null);

    const filteredChannels = (this._tvChannels || []).filter((c) => {
      const matchFilter = this._tvFilter === "all" || c.category === this._tvFilter;
      const matchSearch =
        !this._tvSearch ||
        c.name.toLowerCase().includes(this._tvSearch.toLowerCase()) ||
        (c.num && String(c.num).includes(this._tvSearch));
      return matchFilter && matchSearch;
    });

    const categories = ["all", "Généraliste", "Information", "Culture", "Jeunesse", "Sport", "Musique", "Régionale"];

    return `
      <div class="tv-container">
        <!-- Box Identification Banner -->
        <div class="box-info-card">
          <div class="box-info-left">
            <div class="box-icon">${boxIcon}</div>
            <div>
              <div class="box-title">
                ${box.name}
                <span class="box-badge">${box.badge || "Connecté"}</span>
              </div>
              <div class="box-desc">${box.description}</div>
            </div>
          </div>
          <div style="text-align: right; color: #8b949e; font-size: 13px;">
            <span>${this._tvChannels.length} chaîne(s) disponible(s)</span>
          </div>
        </div>

        <!-- TV Player Card with Fullscreen & Controls -->
        <div class="tv-player-card">
          <div class="tv-player-header">
            <div class="tv-channel-title">
              ${ch && ch.num ? `<span class="tv-ch-num">CH ${ch.num}</span>` : ""}
              <span class="tv-ch-name">${ch ? ch.name : "Aucune chaîne sélectionnée"}</span>
              <span class="tv-live-tag">🔴 EN DIRECT</span>
            </div>
            <div class="tv-header-actions">
              <button class="btn-tv-action" id="btn-pin-channel" title="Ajouter cette chaîne dans la grille de vos caméras">
                📌 Épingler aux Caméras
              </button>
              <button class="btn-tv-action" id="btn-pip-player" title="Incrustation d'image (Picture-in-Picture)">
                🪟 PiP
              </button>
              <button class="btn-tv-action primary" id="btn-fullscreen-player" title="Passer en plein écran">
                ⛶ Plein Écran
              </button>
            </div>
          </div>

          <div class="tv-player-wrapper" id="tv-player-wrapper">
            <video id="tv-video-player" playsinline autoplay controls></video>
          </div>
        </div>

        <!-- Channel Selector -->
        <div class="tv-selector-card">
          <div class="tv-selector-header">
            <div class="category-pills">
              ${categories
                .map(
                  (cat) => `
                <button class="category-pill ${this._tvFilter === cat ? "active" : ""}" data-category="${cat}">
                  ${cat === "all" ? "Toutes les chaînes" : cat}
                </button>
              `
                )
                .join("")}
            </div>

            <div class="tv-search-box">
              <span class="tv-search-icon">🔍</span>
              <input type="text" class="tv-search-input" id="tv-search-input" placeholder="Rechercher une chaîne ou un numéro..." value="${this._tvSearch}" />
            </div>
          </div>

          <div class="channel-grid">
            ${
              filteredChannels.length > 0
                ? filteredChannels
                    .map((item) => {
                      const isActive = ch && ch.id === item.id;
                      return `
                  <div class="channel-card ${isActive ? "active" : ""}" data-channel-id="${item.id}">
                    <div class="channel-logo-box">
                      ${
                        item.logo
                          ? `<img src="${item.logo}" class="channel-logo-img" alt="${item.name}" />`
                          : `<span style="font-weight: 800; color: #3b82f6;">${item.num || "TV"}</span>`
                      }
                    </div>
                    <div class="channel-details">
                      <div class="channel-name">${item.num ? `${item.num}. ` : ""}${item.name}</div>
                      <div class="channel-sub">${item.category || "Direct"} • ${item.quality || "HD"}</div>
                    </div>
                  </div>
                `;
                    })
                    .join("")
                : `<div style="grid-column: 1 / -1; text-align: center; color: #8b949e; padding: 40px 0;">Aucune chaîne ne correspond à votre recherche.</div>`
            }
          </div>
        </div>
      </div>
    `;
  }

  _renderSettings() {
    return `
      <div class="settings-container">
        <!-- Section 1: Autonomous Wi-Fi Pairing -->
        <div class="settings-card">
          <h3><span>📡</span> Appairage Wi-Fi Autonome (Sans Application Mobile)</h3>
          <p style="color: #8b949e; font-size: 13px; margin: 0 0 16px 0;">
            Connectez vos caméras Wi-Fi (YsxLite, A9, X5, PPPP) directement à votre réseau domestique.
          </p>

          <div style="background: rgba(13, 17, 23, 0.6); padding: 14px; border-radius: 8px; border-left: 3px solid #3b82f6; margin-bottom: 16px; font-size: 13px; line-height: 1.5;">
            <strong>Procédure rapide :</strong><br/>
            1. Allumez la caméra (la LED clignote en bleu = mode Point d'accès).<br/>
            2. Connectez temporairement votre appareil au Wi-Fi de la caméra (ex: <i>AYS-...</i> ou <i>ACCQ-...</i>).<br/>
            3. Renseignez ci-dessous le nom (SSID) et le mot de passe de votre box Wi-Fi, puis cliquez sur <strong>Lancer l'appairage</strong>.
          </div>

          <div class="form-grid">
            <div class="form-group">
              <label for="pair-ssid">SSID de votre Box / Routeur Wi-Fi</label>
              <input type="text" id="pair-ssid" class="form-input" placeholder="Ex: MonReseauWifi" value="${this._pairSsid || ""}" />
            </div>

            <div class="form-group">
              <label for="pair-pass">Mot de passe du Wi-Fi</label>
              <input type="password" id="pair-pass" class="form-input" placeholder="••••••••" value="${this._pairPass || ""}" />
            </div>

            <div class="form-group">
              <label for="pair-ap-ip">IP de la caméra en mode Point d'Accès (Routeur)</label>
              <input type="text" id="pair-ap-ip" class="form-input" value="${this._pairApIp || "192.168.1.1"}" placeholder="Ex: 192.168.1.1 ou 192.168.10.1" />
            </div>
          </div>

          ${
            this._selectedCameraAp
              ? `
            <div style="font-size: 13px; color: #34d399; margin-top: 10px; display: flex; align-items: center; gap: 8px;">
              <span>🎯 Caméra AP sélectionnée :</span>
              <strong style="background: rgba(16, 185, 129, 0.2); padding: 3px 8px; border-radius: 4px; color: #6ee7b7;">${this._selectedCameraAp}</strong>
              <button id="btn-clear-ap-sel" style="background: transparent; border: 1px solid rgba(255,255,255,0.2); color: #94a3b8; border-radius: 4px; padding: 2px 6px; cursor: pointer; font-size: 11px;">✕ Désélectionner</button>
            </div>
          `
              : ""
          }

          ${
            this._detectedAps && this._detectedAps.length > 0
              ? `
            <div style="background: rgba(30, 41, 59, 0.6); padding: 12px 14px; border-radius: 8px; border: 1px solid rgba(59, 130, 246, 0.3); margin-top: 14px;">
              <div style="font-size: 13px; font-weight: 600; color: #93c5fd; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
                <span>🎯 Réseaux Wi-Fi de caméras détectés à proximité :</span>
                <span style="font-size: 11px; color: #94a3b8;">Cliquez sur un réseau pour l'associer</span>
              </div>
              <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                ${this._detectedAps
                  .filter((a) => a.is_camera)
                  .map(
                    (ap) => `
                  <button class="btn-ap-chip" data-ssid="${ap.ssid}" style="background: ${this._selectedCameraAp === ap.ssid ? "#2563eb" : "rgba(15, 23, 42, 0.85)"}; border: 1px solid ${this._selectedCameraAp === ap.ssid ? "#60a5fa" : "#3b82f6"}; color: #fff; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; transition: all 0.2s ease;">
                    📶 <strong>${ap.ssid}</strong> (${ap.signal}%)
                  </button>
                `
                  )
                  .join("")}
                ${this._detectedAps.filter((a) => a.is_camera).length === 0 ? `<div style="font-size: 12px; color: #94a3b8;">Aucun point d'accès caméra identifié. Vérifiez que la caméra clignote en bleu et relancez le scan.</div>` : ""}
              </div>
            </div>
          `
              : ""
          }

          <div style="margin-top: 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
            <button class="btn-primary" id="btn-start-pairing" ${this._pairingActive ? "disabled" : ""}>
              ${this._pairingActive ? "⏳ Appairage en cours..." : "🚀 Lancer l'appairage"}
            </button>
            ${
              this._pairingActive
                ? `<button class="btn-danger" id="btn-stop-pairing">🛑 Annuler l'appairage</button>`
                : ""
            }
            <button class="btn-secondary" id="btn-scan-aps">
              📡 Scanner Wi-Fi Caméras
            </button>
            <button class="btn-secondary" id="btn-scan-lan" ${this._isScanning ? "disabled" : ""}>
              ${this._isScanning ? "⏳ Scan en cours..." : "🔍 Scanner le réseau & Détecter les caméras"}
            </button>
            <button class="btn-secondary" id="btn-show-qr">
              ${this._showQrCode ? "✕ Masquer QR Code" : "📱 Afficher QR Code Caméra"}
            </button>
          </div>

          ${
            this._showQrCode
              ? `
            <div style="background: #ffffff; color: #0f172a; padding: 20px; border-radius: 12px; margin-top: 16px; text-align: center; max-width: 320px; margin-left: auto; margin-right: auto; box-shadow: 0 8px 30px rgba(0,0,0,0.5);">
              <div style="font-weight: 700; font-size: 15px; margin-bottom: 4px; color: #0f172a;">Appairage Optique QR Code</div>
              <div style="font-size: 12px; color: #475569; margin-bottom: 12px;">Pointez l'objectif de la caméra vers ce code à 15-20 cm</div>
              <div id="camera-qr-container" style="display: flex; justify-content: center; margin: 12px 0; min-height: 200px;"></div>
              <div style="font-size: 11px; color: #334155; font-family: monospace; background: #f1f5f9; padding: 6px; border-radius: 6px; word-break: break-all;">
                Réseau : <strong>${this._pairSsid || "Non spécifié"}</strong>
              </div>
            </div>
          `
              : ""
          }

          <!-- Interactive Live Diagnostic Terminal -->
          <div class="terminal-card">
            <div class="terminal-header">
              <div class="terminal-dots">
                <span class="dot-red"></span>
                <span class="dot-yellow"></span>
                <span class="dot-green"></span>
              </div>
              <div class="terminal-title">
                🖥️ Terminal d'Appairage & Diagnostic en Temps Réel
                <span class="terminal-status-badge">${this._pairingActive ? "⏳ ACTIF" : "🟢 PRÊT"}</span>
              </div>
              <button class="btn-clear-terminal" id="btn-clear-logs" title="Effacer l'historique du terminal">Effacer</button>
            </div>
            <div class="pairing-logs" id="pairing-logs">
              ${
                this._pairingLogs && this._pairingLogs.length > 0
                  ? this._pairingLogs.map((l) => `<div>> ${l}</div>`).join("")
                  : `<div style="color: #6ee7b7; opacity: 0.6;">> En attente d'une action (Appairage, Scan réseau ou Ajout de caméra)...</div>`
              }
            </div>
          </div>

          ${
            this._scanSummary
              ? `
            <div class="scan-summary-bar">
              <span class="summary-chip chip-compatible">
                🟢 ${this._scanCompatible.length} Caméras Compatibles (Protocoles intégrés)
              </span>
              <span class="summary-chip chip-incompatible">
                🟠 ${this._scanIncompatible.length} Caméras Détectées (Protocoles Non Intégrés - Cloud / Propriétaire)
              </span>
            </div>
          `
              : ""
          }

          ${
            this._scanCompatible && this._scanCompatible.length > 0
              ? `
            <div class="scan-category-section">
              <div class="scan-category-header" style="color: #34d399;">
                <span>🟢</span>
                <span>Caméras Compatibles avec DomoLink (YsxLite PPPP, RTSP, ONVIF, MJPEG)</span>
                <span style="font-size: 12px; color: #8b949e; font-weight: normal;">— Flux direct local accessible</span>
              </div>
              <div class="discovered-list">
                ${this._scanCompatible
                  .map(
                    (dev) => `
                  <div class="discovered-item compatible">
                    <div style="flex: 1;">
                      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                        <span class="badge-protocol badge-green">${dev.protocol || dev.driver}</span>
                        <strong style="color: #f0f6fc; font-size: 14px;">${dev.name || dev.model}</strong>
                      </div>
                      <div style="font-size: 12px; color: #8b949e;">
                        IP: <code style="color: #60a5fa;">${dev.host}${dev.port ? `:${dev.port}` : ""}</code>
                        ${dev.model ? ` • Modèle : ${dev.model}` : ""}
                      </div>
                      ${
                        dev.details
                          ? `<div style="font-size: 11px; color: #94a3b8; margin-top: 4px;">${dev.details}</div>`
                          : ""
                      }
                    </div>
                    <div>
                      ${
                        dev.already_added
                          ? `<span class="badge-already-added">✓ Déjà intégrée</span>`
                          : `<button class="btn-primary btn-add-discovered" data-host="${dev.host}">+ Ajouter à DomoLink</button>`
                      }
                    </div>
                  </div>
                `
                  )
                  .join("")}
              </div>
            </div>
          `
              : ""
          }

          ${
            this._scanIncompatible && this._scanIncompatible.length > 0
              ? `
            <div class="scan-category-section" style="margin-top: 24px;">
              <div class="scan-category-header" style="color: #fbbf24;">
                <span>🟠</span>
                <span>Autres Caméras Détectées (Protocoles Non Intégrés - Cloud / Propriétaire)</span>
                <span style="font-size: 12px; color: #8b949e; font-weight: normal;">— Flux fermé ou hébergé dans un cloud distant</span>
              </div>
              <div class="discovered-list">
                ${this._scanIncompatible
                  .map(
                    (dev) => `
                  <div class="discovered-item incompatible">
                    <div style="flex: 1;">
                      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px; flex-wrap: wrap;">
                        <span class="badge-protocol badge-orange">${dev.platform}</span>
                        <span class="badge-protocol badge-gray">${dev.protocol}</span>
                        <strong style="color: #f0f6fc; font-size: 14px;">${dev.name}</strong>
                        ${dev.model ? `<span style="font-size: 12px; color: #8b949e;">(${dev.model})</span>` : ""}
                      </div>
                      <div style="font-size: 12px; color: #8b949e;">
                        Entité HA: <code style="color: #e2e8f0;">${dev.entity_id || dev.host}</code>
                      </div>
                      <div class="reason-box">
                        <strong>⚠️ Raison de non-intégration directe :</strong> ${dev.reason}
                        <div style="margin-top: 4px; font-size: 11px; color: #94a3b8;">
                          💡 <em>Astuce : Vous pouvez associer les interrupteurs ou capteurs de présence de cette caméra dans le bandeau inférieur de vos caméras DomoLink.</em>
                        </div>
                      </div>
                    </div>
                  </div>
                `
                  )
                  .join("")}
              </div>
            </div>
          `
              : ""
          }
        </div>

        <!-- Section 2: Camera Configuration & Linked Entities -->
        <div class="settings-card">
          <h3><span>🛠️</span> Configuration des Caméras & Entités Associées</h3>
          <p style="color: #8b949e; font-size: 13px; margin: 0 0 16px 0;">
            Renommez vos caméras, ajustez leur description (affichée en rollover au survol) et liez des switchs/capteurs Home Assistant.
          </p>

          <table class="camera-edit-table">
            <thead>
              <tr>
                <th>Nom</th>
                <th>Description (Rollover)</th>
                <th>Adresse IP</th>
                <th>Modèle / Protocole</th>
                <th>Entités liées (Bandeau bas)</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${
                this._cameras.length === 0
                  ? `<tr><td colspan="6" style="text-align: center; color: #8b949e;">Aucune caméra.</td></tr>`
                  : this._cameras
                      .map(
                        (cam) => `
                    <tr>
                      <td>
                        <input type="text" class="form-input cam-input-name" data-id="${cam.id}" value="${cam.name}" style="width: 140px;" />
                      </td>
                      <td>
                        <input type="text" class="form-input cam-input-desc" data-id="${cam.id}" value="${cam.description || ""}" placeholder="Ex: Salon grand angle" style="width: 200px;" />
                      </td>
                      <td>
                        <input type="text" class="form-input cam-input-host" data-id="${cam.id}" value="${cam.host}" style="width: 130px;" />
                      </td>
                      <td>
                        <select class="form-select cam-input-driver" data-id="${cam.id}">
                          <option value="ysxlite_pppp" ${cam.driver === "ysxlite_pppp" ? "selected" : ""}>YsxLite PPPP</option>
                          <option value="generic_rtsp" ${cam.driver === "generic_rtsp" ? "selected" : ""}>RTSP / ONVIF</option>
                          <option value="ha_proxy" ${cam.driver === "ha_proxy" ? "selected" : ""}>Passerelle HA</option>
                        </select>
                      </td>
                      <td>
                        <select multiple class="form-select cam-input-entities" data-id="${cam.id}" style="height: 60px; width: 220px; font-size: 11px;">
                          ${this._availableEntities
                            .map((e) => {
                              const isSelected = cam.linked_entities && cam.linked_entities.includes(e.entity_id);
                              return `<option value="${e.entity_id}" ${isSelected ? "selected" : ""}>${e.name} (${e.entity_id})</option>`;
                            })
                            .join("")}
                        </select>
                      </td>
                      <td>
                        <div style="display: flex; gap: 8px;">
                          <button class="btn-primary btn-save-cam" data-id="${cam.id}" title="Enregistrer">💾</button>
                          <button class="btn-danger btn-del-cam" data-id="${cam.id}" title="Supprimer">🗑️</button>
                        </div>
                      </td>
                    </tr>
                  `
                      )
                      .join("")
              }
            </tbody>
          </table>

          <div style="margin-top: 20px;">
            <button class="btn-secondary" id="btn-add-manual-cam">+ Ajouter manuellement une caméra</button>
          </div>
        </div>
      </div>
    `;
  }

  _bindEvents() {
    // Tabs
    const tabCams = this.shadowRoot.querySelector("#tab-cameras");
    const tabTv = this.shadowRoot.querySelector("#tab-tv");
    const tabSets = this.shadowRoot.querySelector("#tab-settings");
    if (tabCams) {
      tabCams.onclick = () => {
        this._activeTab = "cameras";
        this.render();
      };
    }
    if (tabTv) {
      tabTv.onclick = () => {
        this._activeTab = "tv";
        this.render();
        if (!this._boxInfo) {
          this._fetchTvData();
        } else if (this._selectedChannel) {
          this._playChannelStream(this._selectedChannel);
        }
      };
    }
    if (tabSets) {
      tabSets.onclick = () => {
        this._activeTab = "settings";
        this.render();
      };
    }

    const gotoSets = this.shadowRoot.querySelector("#btn-goto-settings");
    if (gotoSets) {
      gotoSets.onclick = () => {
        this._activeTab = "settings";
        this.render();
      };
    }

    // Save Layout Button
    const saveLayoutBtn = this.shadowRoot.querySelector("#btn-save-layout");
    if (saveLayoutBtn) {
      saveLayoutBtn.onclick = () => this._saveLayoutOrder();
    }

    // Live Toggles
    const liveBtns = this.shadowRoot.querySelectorAll(".live-btn");
    liveBtns.forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        this._toggleLive(btn.dataset.camId);
      };
    });

    // Entity Badges Toggle
    const entityBadges = this.shadowRoot.querySelectorAll(".entity-badge");
    entityBadges.forEach((badge) => {
      badge.onclick = (e) => {
        e.stopPropagation();
        this._toggleEntity(badge.dataset.entityId);
      };
    });

    // Drag and Drop on Cards
    const cards = this.shadowRoot.querySelectorAll(".camera-card");
    cards.forEach((card) => {
      const idx = parseInt(card.dataset.index, 10);
      card.ondragstart = (e) => this._handleDragStart(e, idx);
      card.ondragover = (e) => this._handleDragOver(e);
      card.ondragenter = (e) => this._handleDragEnter(e);
      card.ondragleave = (e) => this._handleDragLeave(e);
      card.ondrop = (e) => this._handleDrop(e, idx);
      card.ondragend = (e) => this._handleDragEnd(e);
    });

    // Input persistence on typing (prevents resets)
    const ssidInput = this.shadowRoot.querySelector("#pair-ssid");
    if (ssidInput) {
      ssidInput.oninput = (e) => {
        this._pairSsid = e.target.value.trim();
        try { localStorage.setItem("domolink_pair_ssid", this._pairSsid); } catch (err) {}
      };
    }

    const passInput = this.shadowRoot.querySelector("#pair-pass");
    if (passInput) {
      passInput.oninput = (e) => {
        this._pairPass = e.target.value;
        try { localStorage.setItem("domolink_pair_pass", this._pairPass); } catch (err) {}
      };
    }

    const apIpInput = this.shadowRoot.querySelector("#pair-ap-ip");
    if (apIpInput) {
      apIpInput.oninput = (e) => {
        this._pairApIp = e.target.value.trim();
        try { localStorage.setItem("domolink_pair_ap_ip", this._pairApIp); } catch (err) {}
      };
    }

    // Pairing buttons
    const startPairBtn = this.shadowRoot.querySelector("#btn-start-pairing");
    if (startPairBtn) {
      startPairBtn.onclick = () => this._startPairing();
    }

    const stopPairBtn = this.shadowRoot.querySelector("#btn-stop-pairing");
    if (stopPairBtn) {
      stopPairBtn.onclick = () => this._stopPairing();
    }

    const scanApsBtn = this.shadowRoot.querySelector("#btn-scan-aps");
    if (scanApsBtn) {
      scanApsBtn.onclick = () => this._scanCameraAps();
    }

    const scanLanBtn = this.shadowRoot.querySelector("#btn-scan-lan");
    if (scanLanBtn) {
      scanLanBtn.onclick = () => this._scanLocalNetwork();
    }

    const showQrBtn = this.shadowRoot.querySelector("#btn-show-qr");
    if (showQrBtn) {
      showQrBtn.onclick = () => {
        this._showQrCode = !this._showQrCode;
        this.render();
      };
    }

    const clearApBtn = this.shadowRoot.querySelector("#btn-clear-ap-sel");
    if (clearApBtn) {
      clearApBtn.onclick = () => {
        this._selectedCameraAp = null;
        this.render();
      };
    }

    const apChips = this.shadowRoot.querySelectorAll(".btn-ap-chip");
    apChips.forEach((btn) => {
      btn.onclick = () => {
        this._selectedCameraAp = btn.dataset.ssid;
        this._pairApIp = "192.168.1.1";
        this._appendLog(`🎯 Point d'accès caméra sélectionné : ${btn.dataset.ssid}`);
        this.render();
      };
    });

    if (this._showQrCode && window.QRCode) {
      const qrTarget = this.shadowRoot.querySelector("#camera-qr-container");
      if (qrTarget) {
        qrTarget.innerHTML = "";
        const qrString = `WIFI:T:WPA;S:${this._pairSsid || ""};P:${this._pairPass || ""};;`;
        try {
          new window.QRCode(qrTarget, {
            text: qrString,
            width: 200,
            height: 200,
            correctLevel: window.QRCode.CorrectLevel.M,
          });
        } catch (e) {
          qrTarget.innerHTML = `<div style="color: red; font-size: 12px;">Erreur génération QR : ${e.message || e}</div>`;
        }
      }
    }

    const clearLogsBtn = this.shadowRoot.querySelector("#btn-clear-logs");
    if (clearLogsBtn) {
      clearLogsBtn.onclick = () => {
        this._pairingLogs = [];
        this._updatePairingLogs();
      };
    }

    const addDiscoveredBtns = this.shadowRoot.querySelectorAll(".btn-add-discovered");
    addDiscoveredBtns.forEach((btn) => {
      btn.onclick = () => {
        const dev = (this._scanCompatible || this._scanResults || []).find((d) => d.host === btn.dataset.host);
        if (dev) this._addDiscoveredCamera(dev);
      };
    });

    // Save individual camera
    const saveCamBtns = this.shadowRoot.querySelectorAll(".btn-save-cam");
    saveCamBtns.forEach((btn) => {
      btn.onclick = () => {
        const id = btn.dataset.id;
        const nameInp = this.shadowRoot.querySelector(`.cam-input-name[data-id="${id}"]`);
        const descInp = this.shadowRoot.querySelector(`.cam-input-desc[data-id="${id}"]`);
        const hostInp = this.shadowRoot.querySelector(`.cam-input-host[data-id="${id}"]`);
        const driverInp = this.shadowRoot.querySelector(`.cam-input-driver[data-id="${id}"]`);
        const entSelect = this.shadowRoot.querySelector(`.cam-input-entities[data-id="${id}"]`);

        const selectedEntities = Array.from(entSelect ? entSelect.selectedOptions : []).map((o) => o.value);

        const current = this._cameras.find((c) => c.id === id) || {};
        const updated = {
          ...current,
          id: id,
          name: nameInp ? nameInp.value.trim() : current.name,
          description: descInp ? descInp.value.trim() : "",
          host: hostInp ? hostInp.value.trim() : current.host,
          driver: driverInp ? driverInp.value : current.driver,
          linked_entities: selectedEntities,
        };

        this._saveCamera(updated);
      };
    });

    // Delete camera
    const delCamBtns = this.shadowRoot.querySelectorAll(".btn-del-cam");
    delCamBtns.forEach((btn) => {
      btn.onclick = () => this._deleteCamera(btn.dataset.id);
    });

    // Add manual camera
    const addManualBtn = this.shadowRoot.querySelector("#btn-add-manual-cam");
    if (addManualBtn) {
      addManualBtn.onclick = () => {
        const newCam = {
          name: "Nouvelle Caméra",
          description: "Caméra configurée manuellement",
          driver: "ysxlite_pppp",
          host: "192.168.1.100",
          port: 32108,
          linked_entities: [],
        };
        this._saveCamera(newCam);
      };
    }

    // --- TV Tab Controls & Fullscreen ---
    const fsBtn = this.shadowRoot.querySelector("#btn-fullscreen-player");
    if (fsBtn) {
      fsBtn.onclick = () => this._toggleFullscreen();
    }

    const pipBtn = this.shadowRoot.querySelector("#btn-pip-player");
    if (pipBtn) {
      pipBtn.onclick = () => this._togglePip();
    }

    const pinBtn = this.shadowRoot.querySelector("#btn-pin-channel");
    if (pinBtn) {
      pinBtn.onclick = () => this._pinCurrentChannel();
    }

    const tvVideo = this.shadowRoot.querySelector("#tv-video-player");
    if (tvVideo) {
      tvVideo.ondblclick = () => this._toggleFullscreen();
    }

    // Category pills filter
    const catPills = this.shadowRoot.querySelectorAll(".category-pill");
    catPills.forEach((pill) => {
      pill.onclick = () => {
        this._tvFilter = pill.dataset.category;
        this.render();
      };
    });

    // Search input
    const searchInp = this.shadowRoot.querySelector("#tv-search-input");
    if (searchInp) {
      searchInp.oninput = (e) => {
        this._tvSearch = e.target.value;
        const grid = this.shadowRoot.querySelector(".channel-grid");
        if (grid) {
          const filtered = (this._tvChannels || []).filter((c) => {
            const matchFilter = this._tvFilter === "all" || c.category === this._tvFilter;
            const matchSearch =
              !this._tvSearch ||
              c.name.toLowerCase().includes(this._tvSearch.toLowerCase()) ||
              (c.num && String(c.num).includes(this._tvSearch));
            return matchFilter && matchSearch;
          });

          grid.innerHTML =
            filtered.length > 0
              ? filtered
                  .map((item) => {
                    const isActive = this._selectedChannel && this._selectedChannel.id === item.id;
                    return `
                  <div class="channel-card ${isActive ? "active" : ""}" data-channel-id="${item.id}">
                    <div class="channel-logo-box">
                      ${
                        item.logo
                          ? `<img src="${item.logo}" class="channel-logo-img" alt="${item.name}" />`
                          : `<span style="font-weight: 800; color: #3b82f6;">${item.num || "TV"}</span>`
                      }
                    </div>
                    <div class="channel-details">
                      <div class="channel-name">${item.num ? `${item.num}. ` : ""}${item.name}</div>
                      <div class="channel-sub">${item.category || "Direct"} • ${item.quality || "HD"}</div>
                    </div>
                  </div>
                `;
                  })
                  .join("")
              : `<div style="grid-column: 1 / -1; text-align: center; color: #8b949e; padding: 40px 0;">Aucune chaîne trouvée.</div>`;

          this._bindChannelCards();
        }
      };
    }

    // Channel cards click
    this._bindChannelCards();
  }

  _bindChannelCards() {
    const chCards = this.shadowRoot.querySelectorAll(".channel-card");
    chCards.forEach((card) => {
      card.onclick = () => {
        const chId = card.dataset.channelId;
        const channel = (this._tvChannels || []).find((c) => c.id === chId);
        if (channel) {
          this._selectedChannel = channel;
          chCards.forEach((c) => c.classList.remove("active"));
          card.classList.add("active");
          const nameEl = this.shadowRoot.querySelector(".tv-ch-name");
          if (nameEl) nameEl.textContent = channel.name;
          const numEl = this.shadowRoot.querySelector(".tv-ch-num");
          if (numEl) numEl.textContent = channel.num ? `CH ${channel.num}` : "";
          this._playChannelStream(channel);
        }
      };
    });
  }
}

customElements.define("domolink-camera-panel", DomolinkCameraPanel);
