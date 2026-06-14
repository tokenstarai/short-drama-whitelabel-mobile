import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/short_drama_app.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

void main() {
  testWidgets('language picker updates shell and account labels', (
    tester,
  ) async {
    await tester.pumpWidget(ShortDramaApp(flavor: FlavorConfig.hongguo()));

    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Mine'), findsOneWidget);

    await tester.tap(find.text('Mine'));
    await tester.pumpAndSettle();
    expect(find.text('Language'), findsOneWidget);

    await tester.tap(find.text('Language'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('中文'));
    await tester.pumpAndSettle();

    expect(find.text('首页'), findsOneWidget);
    expect(find.text('我的'), findsOneWidget);
    expect(find.text('钱包中心'), findsOneWidget);
    expect(find.text('语言'), findsOneWidget);
  });
}
