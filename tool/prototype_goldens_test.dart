import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../test/prototype_test_support.dart';

void main() {
  for (final flavorEntry in prototypeFlavors.entries) {
    for (final screen in prototypeScreens) {
      testWidgets('${flavorEntry.key} ${screen.label} 390px prototype', (
        tester,
      ) async {
        await pumpPrototypeScreen(
          tester,
          flavor: flavorEntry.value(),
          screen: screen,
          width: 390,
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(
            '../test/goldens/prototypes/${flavorEntry.key}_${screen.id}.png',
          ),
        );
      });
    }
  }
}
