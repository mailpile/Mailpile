#!/usr/bin/env python2.7
#
# This is a small experiment in assigning colors to key fingerprints (or
# any other fingerprint).
#
# The goal of this might be to make it easier to recognize two fingerprints
# as being the same (or different), and maybe also make something pretty
# that we can use to identify users instead of gravatar icons.
#
# The colors are assigned in such a way that the color shifts are gradual,
# and the ends converge on the same values so the whole thing can be made
# into a circle/wheel if necessary. By omitting one slice, a keyhole or
# angel is created, which fits nicely with ideas of identity and privacy.
#
# The color blending used makes the end result more visually appealing,
# and a bit less "random" - creating patterns which help with recall. The
# downside (aside from color-blindness related issues), is we lose about
# 50% of the bits of the fingerprint. To compensate for this, the low-order
# bits of each hex pair are used to vary the hight of each color slice.
# Another strategy would be to double the number of slices.
#
# Finally, to ensure that fingerprints which differ only slightly (a bit
# flipped here and there) are obviously different, the entire color space
# is shifted by a fixed value derived from the MD5 of the original
# fingerprint.
#
import datetime
import os
import hashlib
import subprocess

canvastest = """
<!DOCTYPE html>
<html><head>
  <style>
    body { background: #fff; }
  </style>
  <script>
  function getWheel(box, points) {
    var c = document.createElement("canvas");
    c.setAttribute("width", box);
    c.setAttribute("height", box);
    var ctx = c.getContext("2d");
    var step = (2 * Math.PI) / points.length;
    var shift = (0.5 * Math.PI) + (step/2);
    var maxwidth = box/3;
    var pair = function(char, color, scale) {
      var sh = shift;
      var beg = sh + char*step;
      var height = scale * maxwidth;
      ctx.beginPath();
      ctx.arc(box/2, box/2, box/2 - maxwidth + height/2, beg, beg + step);
      ctx.lineWidth = height;
      ctx.strokeStyle = color;
      ctx.stroke();
    };
    ctx.clearRect(0, 0, c.width, c.height);
    for (var i = 0; i < points.length-1; i++) {
      pair(i, points[i][0], points[i][1]);
    }
    return c.toDataURL();
  }
  </script>
</head><body>
  <h2>Visualizing PGP fingerprints as colored keyholes/angels...</h2>

"""

def colorprint(fingerprint, md5shift=True, mixer=[4, 8, 4]):
    fingerprint = fingerprint.replace(' ', '').upper()
    while 0 != ((len(fingerprint)//2) % 3):
        fingerprint += '  '
    l = len(fingerprint)//2

    # Use an MD5 to shift the colorspace randomly, so even bitflips
    # or other small changes become very noticable.
    if md5shift:
        digest = hashlib.md5(fingerprint).hexdigest()
        sr, sg, sb = [int(d, 16) for d in (digest[0:3], digest[3:6], digest[6:9])]
    else:
        digest = '77'
        sr = sg = sb = 0
    def _r(v): return (sr + v) & 0xff;
    def _g(v): return (sg + v) & 0xff;
    def _b(v): return (sb + v) & 0xff;

    # This assigns each hex pair a color, where the RGB values depend on
    # itself and the other pairs around it. Changes are gradual, taking
    # half the color value from immediate neighbors, with those once
    # removed in either direction, mixing in at a quarter each.
    def _int(v):
        if v == '  ':
            return int(digest[-2:], 16)
        return int(v, 16)
    pairs = []
    m1, m2, m3 = mixer
    for i in range(0, len(fingerprint)//2):
        if (i % 3) == 1:
            rgb = [((o+i) % l) for o in (-4, -3, -2, -1,  0,  1,  2,  3,  4)]
        if (i % 3) == 2:
            rgb = [((o+i) % l) for o in (-2, -4, -3,  1, -1,  0,  4,  2,  3)]
        if (i % 3) == 0:
            rgb = [((o+i) % l) for o in (-3, -2, -4,  0,  1, -1,  3,  4,  2)]
 
        rgb = [_int(fingerprint[c*2:c*2+2]) for c in rgb]
        r3 = (m1*_r(rgb[0]) + m2*_r(rgb[3]) + m3*_r(rgb[6])) // 16
        g3 = (m1*_g(rgb[1]) + m2*_g(rgb[4]) + m3*_g(rgb[7])) // 16
        b3 = (m1*_b(rgb[2]) + m2*_b(rgb[5]) + m3*_b(rgb[8])) // 16
        r1 = '%2.2x' % _r(rgb[3])
        g1 = '%2.2x' % _g(rgb[4])
        b1 = '%2.2x' % _b(rgb[5])

        fr, fg, fb = ['%2.2x' % ((4*c)/5 +0x00) for c in (r3, g3, b3)]
        br, bg, bb = ['%2.2x' % ((4*c)/5 +0x33) for c in (r3, g3, b3)]
        rr, gg, bb = ['%2.2x' % c for c in (r3, g3, b3)]

        pairs.append(['#%s%s%s' % (rr, gg, bb),  # Mixed
                      '#%s%s%s' % (r1, g1, b1),  # RGB: Plain
                      '#%s%s%s' % (fr, fg, fb),  # RGB: Foreground
                      '#%s%s%s' % (br, bg, bb),  # RGB: Background
                      _int(fingerprint[i*2:i*2+2]),
                      fingerprint[i*2:i*2+2]])

    return pairs

def colorprint2(fingerprint, md5shift=True):
    fingerprint = fingerprint.replace(' ', '').upper()
    while 0 != ((len(fingerprint)//2) % 3):
        fingerprint += '  '
    l = len(fingerprint)//2

    # Use an MD5 to shift the colorspace randomly, so even bitflips
    # or other small changes become very noticable.
    if md5shift:
        digest = hashlib.md5(fingerprint).hexdigest()
        sr, sg, sb = [int(d, 16) for d in (digest[0:2],
                                           digest[2:4],
                                           digest[4:6])]
    else:
        digest = '77'
        sr = sg = sb = 0
    def _r(v): return (sr + v) & 0xff;
    def _g(v): return (sg + v) & 0xff;
    def _b(v): return (sb + v) & 0xff;

    # This assigns each hex pair a color, where the RGB values depend on
    # itself and the other pairs around it. Changes are gradual, taking
    # half the color value from immediate neighbors, with those once
    # removed in either direction, mixing in at a quarter each.
    def _int(v):
        if v == '  ':
            return int(digest[-2:], 16)
        return int(v, 16)
    pairs = []
    for i in range(0, len(fingerprint)//2):
        val = _int(fingerprint[i*2:i*2+2])

        if (i % 3) == 0:
            rgb = [((o+i) % l) for o in ( 0,  1, -1,  0,  1,  2)]
            val = _r(val) 
        if (i % 3) == 1:
            rgb = [((o+i) % l) for o in (-1,  0,  1,  2,  0,  1)]
            val = _g(val) 
        if (i % 3) == 2:
            rgb = [((o+i) % l) for o in ( 1, -1,  0,  1,  2,  0)]
            val = _b(val) 

        rgb = [_int(fingerprint[c*2:c*2+2]) for c in rgb]
        r1 = _r(rgb[0]) & 0xe0  # 0xe0 == 3 bits per channel
        g1 = _g(rgb[1]) & 0xe0
        b1 = _b(rgb[2]) & 0xe0
        rm = (r1 + _r(rgb[3])) // 2
        gm = (g1 + _g(rgb[4])) // 2
        bm = (b1 + _b(rgb[5])) // 2

        # Reverse the bits of val, so low order bits get more importance.
        # This exposes what would be too subtle a color change, as a spacial
        # change instead.
        rval = 0
        for j in range(0, 8):
            rval += (0x80 >> j) if (val & (1 << j)) else 0

        sbtR = (val & 0xb0)
        sbtG = (val & 0x30) << 2
        sbtB = (val & 0x0b) << 4

        pairs.append(['#%2.2x%2.2x%2.2x' % (sbtR, sbtG, sbtB),  # sixbytwo
                      '#%2.2x%2.2x%2.2x' % (r1, g1, b1),        # RGB
                      '#%2.2x%2.2x%2.2x' % (rm, gm, bm),        # Mixed
                      val,
                      rval & 0xe0,        # 0xc0 == 2 bits per channel
                      val & 0x18,         # These bits are orphans!
                      fingerprint[i*2:i*2+2]])

    return pairs


def tohtml(cprint, brk=False):
    pairs = []
    for mixed, rgb, fg, bg, val, hexchars in cprint:
        pairs.append(('<span style="background: %s">%s</span>'
                      ) % (rgb, hexchars))
        if brk and ((i % 4) == 3):
            pairs.append('<br>')
    # Fixed width font, so all our rainbows have the same proportions.
    return '<tt>%s</tt>\n' % ''.join(pairs)

def toangel(slices, fingerprint, copy=True, size=64):
    return ''.join(['<span class=angel title="%s">' % fingerprint,
                    ('<script>document.write("<img '
                     'src=\'"+getWheel(%s, %s)+"\'>");</script>'
                     ) % (size, slices, ),
                    (('<script>document.write("<input type=text '
                      'value=\'"+getWheel(%s, %s)+"\'>");</script>'
                      ) % (size, slices, )) if copy else '',
                    '</span>\n'])

if os.getenv('HTTP_METHOD'):
   print 'Content-Type: text/html'
   print
print canvastest

fingerprint = "A3C4 F0F9 79CA A22C DBA8  F512 EE8C BC9E 886D DD89"
cprint = colorprint(fingerprint, md5shift=False)
print '<b>Channels:</b> ', tohtml(cprint), '<br>'

print '<h4>Channels, +mixing, +sizes, +md5shift</h4>'
print toangel([[rgb, 1] for mixed, rgb, fg, bg, val, hc in cprint],
              fingerprint)
print toangel([[mixed, 1] for mixed, rgb, fg, bg, val, hc in cprint],
              fingerprint), '<br>'
print toangel([[mixed, 0.5 + float(val % 32)/64]
                for mixed, rgb, fg, bg, val, hc in cprint],
              fingerprint)
cprint = colorprint(fingerprint, md5shift=True)
print toangel([[mixed, 0.5 + float(val % 32)/64]
                for mixed, rgb, fg, bg, val, hc in cprint],
              fingerprint), '<br>'

print '<h4>1 bit flipped, w/o or with md5shift</h4>'
fingerprint = "A3C4 F0F8 79CA A22C DBA8  F512 EE8C BC9E 886D DD89"
cprint = colorprint(fingerprint, md5shift=False)
print toangel([[mixed, 0.5 + float(val % 32)/64]
                for mixed, rgb, fg, bg, val, hc in cprint],
              fingerprint)
cprint = colorprint(fingerprint, md5shift=True)
print toangel([[mixed, 0.5 + float(val % 32)/64]
                for mixed, rgb, fg, bg, val, hc in cprint],
              fingerprint), '<br>'

print '<h4>New style colorprinting tests: 6x2 palette, channels, mixed</h4>'
fingerprint = "A3C4 F0F9 79CA A22C DBA8  F512 EE8C BC9E 886D DD89"
cprint2 = colorprint2(fingerprint, md5shift=False)
print toangel([[sixtimestwo, 1.0 - float(rval)/512]
                for sixtimestwo, rgb, mixed, val, rval, dr, hc in cprint2],
              fingerprint)
print toangel([[rgb, 1.0 - float(rval)/512]
                for sixtimestwo, rgb, mixed, val, rval, dr, hc in cprint2],
              fingerprint)
print toangel([[mixed, 1.0 - float(rval)/512]
                for sixtimestwo, rgb, mixed, val, rval, dr, hc in cprint2],
              fingerprint), '<br>'

print '<h4>Adding md5shift, checking bit flips</h4>'
cprint2 = colorprint2(fingerprint, md5shift=True)
print toangel([[mixed, 1.0 - float(rval)/512]
                for sixtimestwo, rgb, mixed, val, rval, dr, hc in cprint2],
              fingerprint)
fingerprint = "A3C4 F0F8 79CA A22C DBA8  F512 EE8C BC9E 886D DD89"
cprint2b = colorprint2(fingerprint, md5shift=True)
print toangel([[mixed, 1.0 - float(rval)/512]
                for sixtimestwo, rgb, mixed, val, rval, dr, hc in cprint2b],
              fingerprint), '<br>'

print "<hr><h3>More samples (new style, full features)</h3>"
count = 0
for line in """\
      Key fingerprint = A3C4 F0F9 79CA A22C DBA8  F512 EE8C BC9E 886D DD89
      Key fingerprint = 61A0 1576 3D28 D410 A87B  1973 2819 1D9B 3B41 99B4
      Key fingerprint = B221 6FD2 779A E5B5 9D79  743C D5DC 2A79 C2E4 AE92
      Key fingerprint = C8F9 EBDA 2167 CC5F 4D2B  EDA1 F5C2 529F C903 BEF1
      Key fingerprint = 8779 4923 97B2 0AA4 998C  0EA6 AED2 48B1 C7B2 CAC3
      Key fingerprint = 7670 B684 846E C70E 61EF  FB7F 07AA A4D9 5F3D 6695
      Key fingerprint = 7960 1CDC 85C9 0B63 8D9F  DD89 3BD8 FF2B 807B 17C1
      Key fingerprint = 2139 09EF B5EC 48DC 9129  D778 53C8 B358 6156 D52D
      Key fingerprint = 228F AD20 3DE9 AE7D 84E2  5265 CF9A 6F91 4193 A197
      Key fingerprint = 6F10 0BDF B3B6 A1EA 31E8  54D1 46D0 A5AD 7050 73B5
      Key fingerprint = D95C 3204 2EE5 4FFD B25E  C348 9F27 33F4 0928 D23A
      Key fingerprint = E413 80A8 4EB7 30BB 8E5B  8355 B327 24B9 61FE DFBA
      Key fingerprint = 3D6A 08E9 1262 3E9A 00B2  1BDC 067F 4920 98CF 2762
      Key fingerprint = 20FF 4163 4DF6 F90E CA44  5220 3CAC 6CA6 E4D9 C373
      Key fingerprint = B906 EA4B 8A28 15C4 F859  6F9F 47C1 3F3F ED73 5179
""".splitlines():
    if 'Key fingerprint' in line:
        fingerprint = line.split(' = ', 1)[1].strip()
        cprint = colorprint2(fingerprint)
        print toangel([[mixed, 1.0 - float(rval)/512]
                       for sixXtwo, rgb, mixed, val, rval, dr, hc in cprint],
                      fingerprint, copy=False, size=128)
        count += 1
        if count % 5 == 0:
            print '<br>'

print '<hr>'
print 'Generated: %s' % datetime.datetime.now().ctime()
print '</body></html>'

