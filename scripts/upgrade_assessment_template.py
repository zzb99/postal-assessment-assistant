"""Narrow OOXML layout repair; preserve every other original ZIP part byte-for-byte."""
import argparse
from copy import deepcopy
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}


def node(parent, name, **attrs):
    found = parent.find('w:' + name, NS)
    if found is None: found = E.SubElement(parent, '{' + W + '}' + name)
    for key, value in attrs.items(): found.set('{' + W + '}' + key, str(value))
    return found


def upgrade(source, output):
    with ZipFile(source) as zin, ZipFile(output, 'w', ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == 'word/document.xml':
                root = E.fromstring(data)
                body = root.xpath('.//w:sdt[w:sdtPr/w:tag/@w:val="ASSESSMENT_CONTENT"]', namespaces=NS)[0]
                paragraph = body.getparent(); cell = paragraph.getparent()
                # Original blank rows supplied the visible ~330pt writing area.
                # Replace that accidental empty-paragraph sizing with an explicit
                # minimum matching the original reference PNG; keep the same table.
                row = cell.getparent()
                node(node(row, 'trPr'), 'trHeight', val=6600, hRule='atLeast')
                for p in list(cell.findall('w:p', NS)):
                    if p is not paragraph: cell.remove(p)
                props = node(paragraph, 'pPr')
                node(props, 'jc', val='both')
                node(props, 'ind', firstLine=640, firstLineChars=200)
                node(props, 'spacing', before=0, after=120, line=300, lineRule='auto')
                rpr = node(props, 'rPr')
                node(rpr, 'rFonts', ascii='宋体', hAnsi='宋体', eastAsia='宋体', cs='宋体')
                node(rpr, 'sz', val=32); node(rpr, 'szCs', val=32)
                run = body.find('.//w:r', NS); run.insert(0, deepcopy(rpr))
                footer = root.xpath('.//w:sdt[w:sdtPr/w:tag/@w:val="INSPECTOR_NAME"]', namespaces=NS)[0].getparent()
                props = node(footer, 'pPr'); node(props, 'jc', val='left')
                tabs = node(props, 'tabs'); node(tabs, 'tab', val='right', pos=9000)
                for rpr in footer.findall('.//w:rPr', NS):
                    node(rpr, 'sz', val=32); node(rpr, 'szCs', val=32)
                    node(rpr, 'rFonts', ascii='宋体', hAnsi='宋体', eastAsia='宋体', cs='宋体')
                for run in footer.findall('w:r', NS):
                    t = run.find('w:t', NS)
                    if t is not None and '填报日期' in (t.text or ''):
                        t.text = '填报日期：'; run.insert(1, E.Element('{' + W + '}tab'))
                data = E.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
            zout.writestr(item, data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source'); parser.add_argument('output')
    args = parser.parse_args()
    upgrade(args.source, args.output)
