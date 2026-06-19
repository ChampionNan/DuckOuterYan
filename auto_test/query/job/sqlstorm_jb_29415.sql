WITH RankedMovies AS (
    SELECT 
        a.id AS movie_id,
        a.title,
        a.production_year,
        a.kind_id,
        a.imdb_index,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.title) AS rank
    FROM 
        aka_title a
    WHERE 
        a.production_year >= 2000
),
Casts AS (
    SELECT 
        c.movie_id,
        COUNT(DISTINCT c.person_id) AS total_cast_members
    FROM 
        cast_info c
    JOIN 
        RankedMovies rm ON c.movie_id = rm.movie_id
    GROUP BY 
        c.movie_id
),
DetailedMovieInfo AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        rm.kind_id,
        c.total_cast_members,
        k.keyword,
        k.phonetic_code,
        m.info
    FROM 
        RankedMovies rm
    LEFT JOIN 
        Casts c ON rm.movie_id = c.movie_id
    LEFT JOIN 
        movie_keyword mk ON rm.movie_id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        movie_info m ON rm.movie_id = m.movie_id
    WHERE 
        m.info_type_id IN (SELECT id FROM info_type WHERE info = 'Box Office')
),
OrderedMovieInfo AS (
    SELECT 
        dmi.*,
        ROW_NUMBER() OVER (ORDER BY dmi.production_year DESC, dmi.title) AS row_num
    FROM 
        DetailedMovieInfo dmi
)
SELECT 
    omi.title,
    omi.production_year,
    omi.total_cast_members,
    omi.keyword,
    omi.info,
    CONCAT(omi.title, ' (', omi.production_year, ')') AS formatted_title
FROM 
    OrderedMovieInfo omi
WHERE 
    omi.row_num <= 10;
