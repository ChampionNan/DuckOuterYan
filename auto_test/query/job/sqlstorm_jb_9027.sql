SELECT
    na.name AS actor_name,
    ti.title AS movie_title,
    ti.production_year,
    co.name AS company_name,
    ct.kind AS company_type,
    COUNT(DISTINCT kc.keyword) AS keyword_count
FROM
    cast_info ci
JOIN
    aka_name na ON ci.person_id = na.person_id
JOIN
    aka_title ti ON ci.movie_id = ti.movie_id
JOIN
    movie_companies mc ON ti.id = mc.movie_id
JOIN
    company_name co ON mc.company_id = co.id
JOIN
    company_type ct ON mc.company_type_id = ct.id
LEFT JOIN
    movie_keyword mk ON ti.id = mk.movie_id
LEFT JOIN
    keyword kc ON mk.keyword_id = kc.id
WHERE
    ti.production_year BETWEEN 2010 AND 2020
    AND ct.kind ILIKE '%film%'
GROUP BY
    na.name, ti.title, ti.production_year, co.name, ct.kind;
