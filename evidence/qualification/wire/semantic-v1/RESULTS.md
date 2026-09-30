# Attitude semantic tests

The original known-value fixture used the identity quaternion, so it could not detect swapped y and z labels. These tests add an asymmetric attitude. The original fixture and its 61-test receipt are unchanged.

The added quaternion is (1, -2, -4, -10)/11. Its squared norm is (1 + 4 + 16 + 100)/121 = 1. Applying the parent-to-body rotation to parent x gives ((1 + 4 - 16 - 100), 2(8 - 10), 2(20 + 4))/121 = (-111, -4, 48)/121. All four components differ, and each is checked by field name. Body angular rates are (1/8, -1/4, 1/2) rad/s.

- The default suite now passes 80 tests.
- The supplemental suite passes 20 tests, including the production encoder's output for this attitude.
- A mutated decoder that swaps `quaternion_y` and `quaternion_z` fails with `semantic component mismatch: quaternion_y`.
- A mutated decoder that conjugates the vector part fails with `semantic component mismatch: quaternion_x`.
- Swapped wire components and swapped angular-rate labels are also rejected.
- Production position, velocity, angular rate and time match the expected bits exactly. The quaternion and the rotated basis match to within the declared 1e-15. The normalized production quaternion differs in its low bits from the ideal rational value, and `production_bits_equal_known` correctly records false.

`summary.json` binds the probe source and receipt, the production bytes, the integer inputs, the test sources, the mutation patches and the original and redacted log hashes. `semantic-receipt.json` lists every named component and the measured basis.
