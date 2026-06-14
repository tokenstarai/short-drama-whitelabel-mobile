import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/short_drama_app.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

void main() {
  testWidgets('mine tab exposes tenant-hosted legal links', (tester) async {
    await tester.pumpWidget(ShortDramaApp(flavor: FlavorConfig.hongguo()));

    await tester.tap(find.text('Mine'));
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(find.text('Terms of Service'), 300);
    expect(find.text('Support'), findsOneWidget);
    expect(find.text('Terms of Service'), findsOneWidget);
    expect(find.text('Privacy Policy'), findsOneWidget);

    await tester.tap(find.text('Terms of Service'));
    await tester.pumpAndSettle();

    expect(find.text('Legal Link'), findsOneWidget);
    expect(
      find.text('https://short-drama-saas-admin-staging.pages.dev/terms'),
      findsOneWidget,
    );
  });
}
