import 'package:flutter_test/flutter_test.dart';

import 'prototype_test_support.dart';

void main() {
  for (final flavorEntry in prototypeFlavors.entries) {
    for (final width in prototypeWidths) {
      testWidgets(
        '${flavorEntry.key} prototype screens fit ${width.toInt()}px',
        (tester) async {
          final flavor = flavorEntry.value();
          for (final screen in prototypeScreens) {
            await pumpPrototypeScreen(
              tester,
              flavor: flavor,
              screen: screen,
              width: width,
            );
            final exception = tester.takeException();
            expect(
              exception,
              isNull,
              reason:
                  '${flavorEntry.key} ${screen.label} overflowed at ${width.toInt()}px: $exception',
            );
          }
        },
      );
    }
  }
}
