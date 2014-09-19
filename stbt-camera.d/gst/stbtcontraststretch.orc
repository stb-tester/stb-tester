.function stbt_contraststretch_apply
.dest 1 out
.source 1 data
.source 1 offset
# Coefficient is 16 bits fixed point with 8 bits after the decimal place
.source 2 coefficient
.temp 1 tmp_8_0
.temp 2 tmp_16_0
.temp 4 out_32_8
.temp 4 out_32_0
.temp 2 out_16_0

subusb tmp_8_0, data, offset           # tmp_8_0 = data - offset
convubw tmp_16_0, tmp_8_0              # tmp_16_0 = (uint16) tmp_8_0
muluwl out_32_8, tmp_16_0, coefficient # out_24_8 = tmp_16_0 * coefficient
shrul out_32_0, out_32_8, 8            # out_32_0 = out_32_8 >> 8
convlw out_16_0, out_32_0              # out_16_0 = (uint16) out_32_0
convsuswb out, out_16_0                # out = (uint8) clamp(out_16_0)
