Set-StrictMode -Version Latest

function ConvertTo-ComparableBackupSchema {
    param([Parameter(Mandatory)][string]$Sql)
    # Restore reparses varchar enum-array casts into per-element text casts.
    # Normalize only simple enum literals in CHECK definitions and index predicates.
    $enumArray = "\(ARRAY\[(?<items>'[A-Za-z_0-9]+'::character varying(?:, '[A-Za-z_0-9]+'::character varying)*)\]\)::text\[\]"
    $lines = foreach ($line in ($Sql -split "`n")) {
        if ($line -match '^(-- Dumped (from database|by pg_dump) version |\\restrict |\\unrestrict )') {
            continue
        }
        if ($line -match '^(    CONSTRAINT [a-z_0-9]+ CHECK |CREATE (UNIQUE )?INDEX [a-z_0-9]+ ON )') {
            [regex]::Replace($line, $enumArray, {
                param($match)
                $items = $match.Groups['items'].Value -split ', '
                'ARRAY[' + (($items | ForEach-Object { "($_)::text" }) -join ', ') + ']'
            })
        } else { $line }
    }
    return ($lines -join "`n").Trim()
}
