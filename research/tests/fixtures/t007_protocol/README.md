# T007 protocol fixtures

Protocol constants are pinned to Pump public docs commit
`1b822158844a60ca577df6ca122211b595a1a578`.

Current strict policy:

- Pump bonding-curve accounts require owner `6EF8...` and the Anchor curve discriminator.
- PumpSwap verified pool accounts require owner `pAMM...` and the 245-byte pool layout.
- The observed 301-byte PumpSwap account shape is not treated as verified until a
  pinned fixture/IDL source proves the layout. It is classified as
  `legacy_observed_layout_pending_fixture` only when explicitly allowed.
