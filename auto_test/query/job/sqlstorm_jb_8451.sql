
SELECT
    t.title AS movie_title,
    a.name AS actor_name,
    ct.kind AS company_type,
    k.keyword AS movie_keyword,
    pi.info AS person_info
FROM
    title t
JOIN
    complete_cast cc ON t.id = cc.movie_id
JOIN
    cast_info ci ON cc.subject_id = ci.id
JOIN
    aka_name a ON ci.person_id = a.person_id
JOIN
    movie_companies mc ON t.id = mc.movie_id
JOIN
    company_name cn ON mc.company_id = cn.id
JOIN
    company_type ct ON mc.company_type_id = ct.id
LEFT JOIN
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN
    keyword k ON mk.keyword_id = k.id
LEFT JOIN
    person_info pi ON a.person_id = pi.person_id
WHERE
    t.production_year BETWEEN 2000 AND 2023
    AND cn.country_code = 'USA'
    AND pi.info_type_id = (SELECT id FROM info_type WHERE info = 'Biography')
GROUP BY
    t.title, a.name, ct.kind, k.keyword, pi.info;
