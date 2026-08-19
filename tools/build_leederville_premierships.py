#!/usr/bin/env python3
"""Build the Leederville CC premiership teams Awards import CSV from the two
'Premiership Teams' sheets."""
import csv, sys

GRADE = {
    '1st': '1st Grade', '2nd': '2nd Grade', '3rd': '3rd Grade', '4th': '4th Grade',
    '5th': '5th Grade', '6th': '6th Grade', '7th': '7th Grade', '8th': '8th Grade',
    'A Res': 'A Reserves', 'B1': 'B1 Grade', 'B2': 'B2 Grade', 'B3': 'B3 Grade',
    'O/D': 'One Day', 'Cs': 'C Grade', 'Ds': 'D Grade', 'Gs': 'G Grade',
}

# (season, grade key, [players]) — captain is the first name, marked with *
TEAMS = [
    # ── Sheet 2: 1954/55 – 1995/96 ──────────────────────────────────────────
    ('1954/55', 'B1', ['F Dans*', 'F Hart', 'A Wemm', 'C Wemm', 'R Wulff', 'J Dobson',
                       'A Evans', 'D Carrick', 'D Cooper', 'K Beay', 'E Drummond']),
    ('1959/60', 'A Res', ['K London*', 'D Summers', 'T Bennetts', 'A Paul', 'F Dans',
                          'L Ellefsen', 'R Wulff', 'P Snow', 'A Evans', 'R Ogden', 'B Parker']),
    ('1963/64', 'B1', ['L Ellefsen*', 'R Owens', 'J Edwards', 'A Paul', 'B Dixon', 'R Wulff',
                       'J Nykyforak', 'A Evans', 'M Hill', 'O Gray']),
    ('1965/66', '1st', ['K London*', 'B Taylor', 'T Bennetts', 'M Jones', 'R Ogden',
                        'J Nykyforak', 'L Billi', 'G Patterson', 'D Cooley', 'R Owens']),
    ('1966/67', 'B1', ['L Ellefsen*', 'R Fowler', 'C Wemm', 'A Braun', 'J Edwards', 'G Povey',
                       'S Smeath', 'C Nairn', 'A Evans', 'B Taylor', 'R Owens', 'J Henderson']),
    ('1968/69', 'B3', ['L Ellefsen*', 'R Fowler', 'A Watling', 'B Morris', 'A Braun', 'J Nichols',
                       'G Povey', 'S Smeath', 'K Kallenberg', 'F Dans', 'P Curley', 'J Kensitt']),
    ('1970/71', '1st', ['K Randell*', 'K London', 'R Stanley', 'G Patterson', 'A Paul', 'F Dans',
                        'D Bruins', 'E Piper', 'I Hunter', 'F Morris', 'R Ogden', 'R Schneider']),
    ('1971/72', '1st', ['K London*', 'R Stanley', 'T Bennetts', 'D Cooley', 'E Piper', 'I Hunter',
                        'G Povey', 'R Panzic', 'R Schneider']),
    ('1972/73', '1st', ['J Nykyforak*', 'J Nichols', 'K Ogden', 'P Curley', 'R Schneider',
                        'S Smeath', 'K London', 'I Hunter', 'B Morris', 'G Carruthers', 'N Durwood']),
    ('1973/74', '1st', ['J Nykyforak*', 'A Watling', 'P Curley', 'R Schneider', 'S Smeath',
                        'K London', 'I Hunter', 'F Morris', 'R Richards', 'B Taylor']),
    ('1974/75', '1st', ['J Nykyforak*', 'A Watling', 'P Curley', 'S Smeath', 'K London',
                        'J Henderson', 'F Morris', 'R Ogden', 'R Schneider']),
    ('1975/76', '1st', ['A Watling*', 'E Watling', 'P Curley', 'K Hart', 'S Smeath', 'J Nykyforak',
                        'L Maggs', 'F Morris', 'R Richards', 'K London']),
    ('1976/77', 'A Res', ['Bob Taylor*', 'W Chapman', 'A Taylor', 'A Paul', 'K London', 'P Gasson',
                          'M McCavana', 'P Semmens', 'G Carruthers', 'M Evans', 'B Morris']),
    ('1977/78', '1st', ['A Watling*', 'J Nykyforak', 'S Smeath', 'P Gasson', 'E Watling',
                        'W Chapman', 'L Maggs', 'F Morris', 'Ray Taylor', 'Barry Taylor']),
    ('1978/79', '1st', ['A Watling*', 'J Nykyforak', 'S Smeath', 'P Gasson', 'S Gasson', 'P Curley',
                        'A Pappadop', 'L Maggs', 'G Sambell', 'R Schneider', 'C Tinknell']),
    ('1981/82', '1st', ['A Watling*', 'R Dastoor', 'S Smeath', 'K Hart', 'L Saxon', 'W Chapman',
                        'J Nykyforak', 'R Walker', 'E Watling', 'P Harries', 'C Tinknell']),
    ('1985/86', '4th', ['P Gasson*', 'J Matthews', 'I Budimir', 'W Chapman', 'T Fullgrabe',
                        'T McInnes', 'S Gasson', 'M Evans', 'R Munns', 'G Chaplin', 'F Williamson']),
    ('1985/86', '6th', ['B Richards*', 'G Connett', 'E Watling', 'P Henderson', 'J Henderson',
                        'C Fullgrabe', 'G Reardon', 'K Andrews', 'S Warder', 'J Perry', 'A Monisse']),
    ('1988/89', '1st', ['D Woods*', 'D Cohen', 'P Harries', 'S Gasson', 'S Smeath', 'J Nykyforak',
                        'D Fitzgerald', 'A Sadiq', 'P Curley', 'M McAlister', 'S Bell']),
    ('1991/92', '1st', ['D Fitzgerald*', 'D Ridden', 'P Henry', 'D Woods', 'D Fullgrabe', 'S Bell',
                        'P Curley', 'J Matthews', 'M Jeps']),
    ('1992/93', '1st', ['D Fitzgerald*', 'P Henry', 'D Woods', 'A Watling', 'R Dastoor', 'P Curley',
                        'M McAlister', 'S Kroenert', 'M Sedgman', 'P Neilson']),
    ('1993/94', '1st', ['D Fitzgerald*', 'D Cohen', 'P Henry', 'D Woods', 'A Watling', 'J Frossos',
                        'S Kroenert', 'M Sedgman', 'P Neilson']),
    ('1993/94', '4th', ['D Fullgrabe*', 'A Wilson', 'R Wilson', 'S Smeath', 'S Gasson', 'M Coore',
                        'D Farrell', 'A Guilfoyle', 'B Houston', 'J Watling', 'T Ziatis']),
    ('1994/95', '1st', ['D Fitzgerald*', 'P Henry', 'D Cohen', 'D Woods', 'G Thomson', 'A Gowers',
                        'P O’Shea', 'M McAlister', 'R Henry', 'S Kroenert', 'P Neilson']),
    ('1994/95', '2nd', ['R Dastoor*', 'B Ogden', 'J Frossos', 'D Williams', 'T Harding', 'A Watling',
                        'J Matthews', 'P Harries', 'D Ferrau', 'J Carcich']),
    ('1994/95', '6th', ['G Gilbert*', 'D Gilbert', 'M Ellis', 'W Chapman', 'W Dickerson', 'S Gasson',
                        'P Markey', 'R Spina', 'D Farrell', 'L Matthews', 'C Houston']),
    ('1995/96', '1st', ['D Woods*', 'D Fitzgerald', 'R Henry', 'D Cohen', 'J Matthews', 'G Thomson',
                        'J Frossos', 'M McAlister', 'D Fullgrabe', 'S Kroenert', 'P Neilson']),

    # ── Sheet 1: 1996/97 – 2020/21 ──────────────────────────────────────────
    ('1996/97', '1st', ['D Woods*', 'D Fitzgerald', 'R Henry', 'D Cohen', 'G Smith', 'G Thomson',
                        'D Ridden', 'M McAlister', 'D Fullgrabe', 'S Kroenert', 'M Beck']),
    ('1996/97', '3rd', ['J Nykyforak*', 'P Gasson', 'W Chapman', 'G Woods', 'D Hicks', 'B Dougan',
                        'P Nichols', 'C Tincknell', 'J O’Connor', 'S Bell', 'A Wilson']),
    ('1997/98', '1st', ['D Woods*', 'D Fitzgerald', 'R Henry', 'D Cohen', 'G Smith', 'G Thomson',
                        'D Ridden', 'M McAlister', 'D Fullgrabe', 'S Kroenert', 'B Purvis']),
    ('1998/99', '1st', ['M McAlister*', 'D Fitzgerald', 'D Woods', 'D Cohen', 'D Fullgrabe',
                        'S Kroenert', 'P Neilson', 'G Smith', 'G Thomson', 'M Pavleka', 'P Nichols']),
    ('1999/00', '1st', ['D Woods*', 'D Cohen', 'M Pavleka', 'D Fitzgerald', 'G Smith', 'G Thomson',
                        'T Ridden', 'G Gilbert', 'S Kroenert', 'D Fullgrabe', 'P Neilson']),
    ('2000/01', '1st', ['D Cohen*', 'M Pavleka', 'D Woods', 'T Wilson', 'G Smith', 'G Gilbert',
                        'R Henry', 'S Kroenert', 'D Ferrau', 'P Neilson']),
    ('2000/01', 'O/D', ['D Farrell*', 'J Matthews', 'M Matthews', 'R Cooke', 'J Gallagher',
                        'M Pratt', 'F Farac', 'N Ridden', 'T Kirkwood', 'J Bonney', 'A Devereaux']),
    ('2003/04', '1st', ['M Pavleka*', 'D Woods', 'T Wilson', 'T Harding', 'S Watling', 'P Nichols',
                        'J Coad', 'S Evans', 'T Ridden', 'B DeGois', 'D Houston']),
    ('2009/10', '1st', ['G Smith*', 'D Cohen', 'D Woods', 'N McInerney', 'T Wilson', 'M Hardy',
                        'J Hughes', 'T Houston', 'C Monarawila', 'G Fernando']),
    ('2010/11', '4th', ['D Ridden*', 'R Pachta', 'R Lanzon', 'J Davey', 'D Williams', 'A Day',
                        'N Daniell', 'R Ruthven', 'R Ridden', 'M Chappell', 'T Kirkwood']),
    ('2010/11', '6th', ['J Frossos*', 'M Sodano', 'A King', 'M O’Dea', 'M Saxon', 'Dan Ferrau',
                        'B DeGois', 'S Senarathne', 'M Lingappa', 'J Bonney', 'B Groves']),
    ('2011/12', '3rd', ['M Evans*', 'R Pachta', 'D Williams', 'R Suares', 'J Coad', 'A King',
                        'D Adamson', 'M Chappell', 'B Groves', 'T Kirkwood']),
    ('2011/12', '7th', ['A Liange*', 'B Barker', 'P Harries', 'N Gamage', 'A Park', 'C Jayasinghe',
                        'G Hall', 'C Mandawalli', 'G Gilbert', 'L Matthews', 'T Bielby',
                        'R Ismalage']),
    ('2012/13', '1st', ['N McInerney*', 'D Cohen', 'D Ridden', 'B Suares', 'S Bilkey',
                        'C Williamson', 'G Smith', 'J Hughes', 'M Hardy', 'D Williams',
                        'C Monarawila']),
    ('2012/13', '5th', ['D Proudmore*', 'T Harrop', 'M Sodano', 'R Maher', 'J Harvey', 'N Lanzon',
                        'N Daniell', 'B DeGois', 'M O’Dea', 'C Fantoni', 'S Bielby',
                        'M Dennis']),
    ('2012/13', '6th', ['B Sloan*', 'B Barker', 'W Chapman', 'R Pachta', 'D Ferrau', 'J Hardy',
                        'S Funston', 'S Ismalage', 'M Lingappa', 'T McInnes']),
    ('2013/14', '7th', ['S Ismalage*', 'G Hall', 'R Ismalage', 'N Gamage', 'M Chappell', 'P Henry',
                        'G Meakins', 'S Drabble', 'S Funston']),
    ('2014/15', '1st', ['M Hardy*', 'D Ridden', 'D Cohen', 'S Bilkey', 'S Cohen', 'J Hughes',
                        'C Williamson', 'R Ruthven', 'C Monarawila', 'B Groves', 'D Williams']),
    ('2015/16', '1st', ['M Hardy*', 'D Ridden', 'M Ennis', 'S Bilkey', 'D Cohen', 'J Hughes',
                        'C Williamson', 'R Ruthven', 'C Monarawila', 'B Groves', 'M O’Dea']),
    ('2015/16', '4th', ['B Sloan*', 'L Hardy', 'J Coad', 'M Coad', 'M Evans', 'B DeGois',
                        'G Gilbert', 'M Dennis', 'CJ Munasinghe', 'M Lingappa', 'C Fantoni']),
    ('2016/17', '8th', ['P Carrich*', 'P Harries', 'T Matthews', 'M Matthews', 'M Adamson',
                        'A D’Ascenzo', 'C Abrams', 'J Egan', 'R James', 'A Fazar',
                        'S Drabble']),
    ('2017/18', '3rd', ['M Dennis*', 'J Leach', 'L Solanki', 'J Coad', 'M Ennis', 'A Boules',
                        'B DeGois', 'D Boules', 'M Evans', 'R Ruthven', 'C Fantoni']),
    ('2018/19', '4th', ['M McCudden*', 'R Gray', 'R Jayasekera', 'M Sodano', 'T Matthews',
                        'A Dennis', 'DL Boules', 'DG Boules', 'K King', 'K Cunningham', 'B Sloan']),
    ('2019/20', 'Cs', ['M Evans*', 'T Harding', 'T Harrop', 'R Henry', 'M Saxon', 'N Blunden',
                       'J Lloyd', 'J Clark', 'B Sheldrick', 'T Kirkwood', 'M Marshall',
                       'D Proudmore']),
    ('2020/21', 'Ds', ['C Fasolo*', 'T McLean', 'L Gardiner', 'B Reynolds', 'K King', 'T Love',
                       'W Bissett', 'M Perrott', 'DG Boules', 'JP Starkie', 'R Henry',
                       'M O’Dea']),
    ('2020/21', 'Gs', ['S Ismalage*', 'A Dharmapriya', 'K Uduwarage', 'N Hobbs',
                       'D Hewathanthrige', 'R Lanzon', 'R Suares', 'C Senevirathne', 'M Mistilis',
                       'R Ismalage', 'C Herath', 'T McInnes']),
]


def season_key(s):
    return int(s.split('/')[0])


def main(path):
    rows = []
    for season, gkey, players in sorted(TEAMS, key=lambda t: (season_key(t[0]), t[1])):
        grade = GRADE[gkey]
        for p in players:
            captain = p.endswith('*')
            name = p[:-1] if captain else p
            rows.append([season, 'Premiership', grade, 'Premiership', name,
                         'Captain' if captain else ''])
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['Season', 'Category', 'Subcategory', 'Achievement', 'Player Name', 'Detail'])
        w.writerows(rows)
    print(f'{len(rows)} rows, {len(TEAMS)} teams, '
          f'{len({r[4] for r in rows})} distinct players -> {path}')


if __name__ == '__main__':
    main(sys.argv[1])
