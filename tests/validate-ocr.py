#!/usr/bin/python3

u"""
validate-ocr.py can be run on a corpus of test images reporting how good a job
stbt has done of reading the text.  Thus it can be used to measure improvements
to the OCR algorithm and, more importantly, detect any regressions introduced.

The corpus consists of a set of images with corresponding text files describing
what the images contain.  e.g. the image `main-menu.png` might have a
corresponding file `main-menu.png.txt` containing:

    lang: deu
    ---
    Recht
    Links
    Oben
    Unten

validate-ocr.py would then check that the result of calling
`ocr('main-menu.png', lang='deu')` contains the text "Recht", "Links", "Oben"
and "Unten" printing a diffable text report to stdout and a human friendly and
more verbose html report to the filename given to `--report-filename`.

Everything above '---' is interpreted as JSON and passed to the ocr() function.

Blank lines are ignored.

This tool is designed such that it can be run on corpuses outside the
stb-tester git tree to allow corpuses containing screen captures from many
set-top boxes without bloating the main stb-tester repo or risking upsetting
the owners of the various set-top box UIs. """

import argparse
import os
import sys

import cv2
import jinja2
import yaml


def check(imgname, phrases, params):
    from stbt_core import ocr

    img = cv2.imread(imgname)
    if img is None:
        raise IOError('No such file or directory "%s"' % imgname)
    text = ocr(img, **params)

    matches = sum(1 for x in phrases if x in text)

    return {
        "matches": matches,
        "total": len(phrases),
        "percentage": float(matches) / len(phrases) * 100,
        "name": os.path.basename(imgname),
        "path": imgname,
        "phrases": [{"text": x, "match": x in text} for x in phrases],
        "text": text,
    }


def main(argv):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report-filename",
                        help="Filename to write the HTML report to")
    parser.add_argument("corpus", help="Directory containing test corpus")

    args = parser.parse_args(argv[1:])

    results = []

    files = []
    for root, _dirs, dfiles in os.walk(args.corpus):
        files += [root + '/' + f for f in dfiles if f.endswith('.png.txt')]

    for n, f in enumerate(files):
        sys.stderr.write("%i / %i Complete\r" % (n, len(files)))

        imgname = f[:-len('.txt')]
        with open(f, encoding='utf-8') as of:
            text = of.read()

        sections = text.split('---', 1)
        if len(sections) == 2:
            params = yaml.safe_load(sections[0])
        else:
            params = {}

        phrases = [x.decode('utf-8') for x in sections[-1].split('\n')
                   if x.strip() != '']
        results.append(check(imgname, phrases, params))

    sys.stderr.write('\n')

    total = sum(x['total'] for x in results)
    total_matched = sum(x['matches'] for x in results)

    if args.report_filename:
        template = os.path.dirname(__file__) + '/validate-ocr.html.jinja'
        with open(args.report_filename, 'w', encoding='utf-8') as f:
            f.write(jinja2.Template(open(template, encoding='utf-8').read())
                    .render(
                images=results,
                total=total,
                total_matched=total_matched,
                percentage=float(total_matched) / total * 100).encode('utf-8'))

    sys.stdout.write("Passes:\n")
    for x in results:
        if x['matches'] > 0:
            sys.stdout.write("    " + x['name'] + '\n')
        for y in x['phrases']:
            if y['match']:
                sys.stdout.write('        ' + y['text'].encode('utf-8') + '\n')

    sys.stdout.write("Failures:\n")
    for x in results:
        if x['matches'] < x['total']:
            sys.stdout.write("    " + x['name'] + '\n')
        for y in x['phrases']:
            if not y['match']:
                sys.stdout.write('        ' + y['text'].encode('utf-8') + '\n')
    return 0 if total == total_matched else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
