WITH RankedTitles AS (
    SELECT 
        a.id AS aka_id,
        a.name AS aka_name,
        a.person_id,
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY t.production_year DESC) AS title_rank
    FROM 
        aka_name a
    JOIN 
        aka_title t ON a.id = t.id
),
ActorMovieDetails AS (
    SELECT 
        c.id AS cast_info_id,
        c.movie_id,
        n.name AS actor_name,
        t.title AS movie_title,
        t.production_year,
        c.nr_order
    FROM 
        cast_info c
    JOIN 
        name n ON c.person_id = n.id
    JOIN 
        title t ON c.movie_id = t.id
),
PopularKeywords AS (
    SELECT 
        mk.movie_id,
        k.keyword,
        COUNT(mk.id) AS keyword_count
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id, k.keyword
),
FilteredMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        pk.keyword,
        pk.keyword_count,
        RANK() OVER (PARTITION BY t.id ORDER BY pk.keyword_count DESC) AS keyword_rank
    FROM 
        title t
    LEFT JOIN 
        PopularKeywords pk ON t.id = pk.movie_id
    WHERE 
        t.production_year > 2000
)
SELECT 
    r.aka_id,
    r.aka_name,
    r.title_id,
    r.title,
    r.production_year,
    amd.actor_name,
    amd.movie_title,
    amd.nr_order,
    fm.keyword AS popular_keyword,
    fm.keyword_count
FROM 
    RankedTitles r
JOIN 
    ActorMovieDetails amd ON r.person_id = amd.movie_id
LEFT JOIN 
    FilteredMovies fm ON amd.movie_id = fm.movie_id AND fm.keyword_rank = 1
WHERE 
    r.title_rank = 1;
