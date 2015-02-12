#!/usr/bin/python
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
import hashlib
import subprocess

canvastest = """
<!DOCTYPE html>
<html><head>
  <style>
    body { background: #fff; }
  </style>
  <script>
  function getWheel(points) {
    var c = document.getElementById("scratch");
    var ctx = c.getContext("2d");
    var step = (2 * Math.PI) / points.length;
    var shift = (0.5 * Math.PI) + (step/2);
    var box = 64;
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
    for (var i = 0; i < points.length; i++) {
      if (points[i][5] != '  ') {
        pair(i, points[i][0], 0.5 + (points[i][4] % 32)/64);
      }
    }
    return c.toDataURL();
  }
  </script>
</head><body>
  <canvas id="scratch" width="64" height="64" style="display: none;"></canvas>
  <p id='output'>A bunch of GPG fingerprints as colored keyholes/angels...</p>

"""

def colorprint(fingerprint):
    fingerprint = fingerprint.replace(' ', '').upper()
    while 0 != ((len(fingerprint)//2) % 3):
        fingerprint += '  '
    l = len(fingerprint)//2

    # Use an MD5 to shift the colorspace randomly, so even bitflips
    # or other small changes become very noticable.
    digest = hashlib.md5(fingerprint).hexdigest()
    sr, sg, sb = [int(d, 16) for d in (digest[0:3], digest[3:6], digest[6:9])]
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
        if (i % 3) == 0: rgb = [((o+i) % l) for o in (-4, -3, -2, -1,  0,  1,  2,  3,  4)]
        if (i % 3) == 1: rgb = [((o+i) % l) for o in (-2, -4, -3,  1, -1,  0,  4,  2,  3)]
        if (i % 3) == 2: rgb = [((o+i) % l) for o in (-3, -2, -4,  0,  1, -1,  3,  4,  2)]
 
        rgb = [_int(fingerprint[c*2:c*2+2]) for c in rgb]
        r3 = (_r(rgb[0]) + 2*_r(rgb[3]) + _r(rgb[6])) // 4
        g3 = (_g(rgb[1]) + 2*_g(rgb[4]) + _g(rgb[7])) // 4
        b3 = (_b(rgb[2]) + 2*_b(rgb[5]) + _b(rgb[8])) // 4
        r1 = '%2.2x' % _r(rgb[3])
        g1 = '%2.2x' % _g(rgb[4])
        b1 = '%2.2x' % _b(rgb[5])

        fr, fg, fb = ['%2.2x' % ((4*c)/5 +0x00) for c in (r3, g3, b3)]
        br, bg, bb = ['%2.2x' % ((4*c)/5 +0x33) for c in (r3, g3, b3)]
        rr, gg, bb = ['%2.2x' % c for c in (r3, g3, b3)]

        pairs.append(['#%s%s%s' % (rr, gg, bb),
                      '#%s%s%s' % (r1, g1, b1),
                      '#%s%s%s' % (fr, fg, fb),
                      '#%s%s%s' % (br, bg, bb),
                      _int(fingerprint[i*2:i*2+2]),
                      fingerprint[i*2:i*2+2]])

    return pairs

def tohtml(cprint, brk=False):
    pairs = []
    for xx, yy, fg, bg, val, hexchars in cprint:
        pairs.append(('<span style="color: %s; background: %s">%s</span>'
                      ) % (fg, bg, hexchars))
        if brk and ((i % 4) == 3):
            pairs.append('<br>')
    # Fixed width font, so all our rainbows have the same proportions.
    return '<tt>%s</tt>' % ''.join(pairs)

print canvastest
gpg = subprocess.Popen(['gpg', '--fingerprint', '--list-keys'],
                       stdout=subprocess.PIPE)
for line in gpg.stdout:
    if 'Key fingerprint' in line:
        fingerprint = line.split(' = ', 1)[1].strip()
        cprint = colorprint(fingerprint)
        print '<span title="%s">' % fingerprint
        print ('<script>document.write("<img src=\'"+getWheel(%s)+"\'>");'
               '</script>') % (cprint,)
        print '</span>\n' # % tohtml(cprint)
print '</body></html>'
