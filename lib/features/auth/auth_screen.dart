import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/app_runtime.dart';
import '../../core/api/app_models.dart';
import '../../core/config/app_capabilities.dart';
import '../../core/i18n/app_strings.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';

typedef OAuthUrlLauncher = Future<bool> Function(Uri uri);

abstract class OAuthCallbackLinks {
  Future<Uri?> getInitialLink();

  Stream<Uri> get uriLinkStream;
}

class SystemOAuthCallbackLinks implements OAuthCallbackLinks {
  SystemOAuthCallbackLinks({AppLinks? appLinks})
      : _appLinks = appLinks ?? AppLinks();

  final AppLinks _appLinks;

  @override
  Future<Uri?> getInitialLink() {
    return _appLinks.getInitialLink();
  }

  @override
  Stream<Uri> get uriLinkStream => _appLinks.uriLinkStream;
}

class OAuthCallbackPayload {
  const OAuthCallbackPayload({
    required this.code,
    this.provider,
    this.oauthStartId,
    this.state,
  });

  final String code;
  final String? provider;
  final String? oauthStartId;
  final String? state;
}

class AuthScreen extends StatefulWidget {
  const AuthScreen({
    required this.flavor,
    this.launchOAuthUrl = _launchOAuthUrl,
    this.callbackLinks,
    super.key,
  });

  final FlavorConfig flavor;
  final OAuthUrlLauncher launchOAuthUrl;
  final OAuthCallbackLinks? callbackLinks;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

Future<bool> _launchOAuthUrl(Uri uri) {
  return launchUrl(uri, mode: LaunchMode.externalApplication);
}

class _AuthScreenState extends State<AuthScreen> {
  final emailController = TextEditingController(text: 'guest@example.com');
  final emailCodeController = TextEditingController(text: '123456');
  final oauthCodeController = TextEditingController();
  final oauthStateController = TextEditingController();
  late final OAuthCallbackLinks callbackLinks;
  StreamSubscription<Uri>? oauthCallbackSubscription;
  bool oauthCallbackListening = false;
  bool submitting = false;
  String? resultText;
  String? errorText;
  String? emailChallengeId;
  String? oauthProvider;
  String? oauthStartId;

  @override
  void initState() {
    super.initState();
    callbackLinks = widget.callbackLinks ?? SystemOAuthCallbackLinks();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!oauthCallbackListening) {
      oauthCallbackListening = true;
      startOAuthCallbackListening();
    }
  }

  @override
  void dispose() {
    oauthCallbackSubscription?.cancel();
    emailController.dispose();
    emailCodeController.dispose();
    oauthCodeController.dispose();
    oauthStateController.dispose();
    super.dispose();
  }

  void startOAuthCallbackListening() {
    callbackLinks.getInitialLink().then((uri) {
      if (uri != null) {
        handleOAuthCallbackUri(uri);
      }
    }).catchError((Object error) {
      if (mounted) {
        setState(() {
          errorText = authErrorMessage(
            AppRuntimeScope.of(context).strings,
            error,
          );
        });
      }
    });
    try {
      oauthCallbackSubscription = callbackLinks.uriLinkStream.listen(
        handleOAuthCallbackUri,
        onError: (Object error) {
          if (mounted) {
            setState(() {
              errorText = authErrorMessage(
                AppRuntimeScope.of(context).strings,
                error,
              );
            });
          }
        },
      );
    } catch (error) {
      if (mounted) {
        setState(() {
          errorText = authErrorMessage(
            AppRuntimeScope.of(context).strings,
            error,
          );
        });
      }
    }
  }

  Future<void> startProvider(AuthProvider provider) async {
    final runtime = AppRuntimeScope.of(context);
    setState(() {
      submitting = true;
      resultText = null;
      errorText = null;
    });
    try {
      _ensureAuthProviderEnabled(runtime, provider.wireValue);
      if (provider == AuthProvider.email) {
        final email = emailController.text.trim();
        if (email.isEmpty) {
          throw ArgumentError('Email is required.');
        }
        final result = await runtime.client.startEmailAuth(
          email: email,
          endUserRef: runtime.endUserRef,
        );
        if (!mounted) {
          return;
        }
        setState(() {
          emailChallengeId = result.challengeId;
          resultText =
              'Email challenge ${result.challengeId} sent to ${result.emailMasked}.';
        });
      } else {
        final result = await runtime.client.startOAuth(
          provider: provider.wireValue,
          endUserRef: runtime.endUserRef,
        );
        if (runtime.isDemoMode) {
          final completed = await runtime.client.completeOAuth(
            provider: result.provider,
            oauthStartId: result.oauthStartId,
            code: 'demo-oauth-code',
            state: 'demo',
            endUserRef: runtime.endUserRef,
          );
          runtime.applyAuthenticatedAccount(completed.account);
          if (!mounted) {
            return;
          }
          setState(() {
            oauthProvider = result.provider;
            oauthStartId = result.oauthStartId;
            resultText =
                '${completed.provider} demo sign-in completed for ${completed.account.accountRefMasked}.';
          });
          return;
        }
        final authUri = Uri.tryParse(result.authUrl);
        if (authUri == null || !authUri.hasScheme) {
          throw StateError('Tenant OAuth URL is unavailable.');
        }
        final launched = await widget.launchOAuthUrl(authUri);
        if (!launched) {
          throw StateError('Unable to open tenant OAuth URL.');
        }
        if (!mounted) {
          return;
        }
        setState(() {
          oauthProvider = result.provider;
          oauthStartId = result.oauthStartId;
          resultText =
              '${result.provider} sign-in opened for tenant ${result.tenantId}.';
        });
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        errorText = authErrorMessage(runtime.strings, error);
      });
    } finally {
      if (mounted) {
        setState(() {
          submitting = false;
        });
      }
    }
  }

  Future<void> verifyEmailChallenge() async {
    final runtime = AppRuntimeScope.of(context);
    final challengeId = emailChallengeId;
    setState(() {
      submitting = true;
      errorText = null;
    });
    try {
      if (challengeId == null) {
        throw StateError('Start email login first.');
      }
      final code = emailCodeController.text.trim();
      if (code.isEmpty) {
        throw ArgumentError('Verification code is required.');
      }
      final result = await runtime.client.verifyEmailAuth(
        challengeId: challengeId,
        code: code,
        endUserRef: runtime.endUserRef,
      );
      runtime.applyAuthenticatedAccount(result.account);
      if (!mounted) {
        return;
      }
      setState(() {
        resultText = 'Email verified for ${result.account.accountRefMasked}.';
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        errorText = authErrorMessage(runtime.strings, error);
      });
    } finally {
      if (mounted) {
        setState(() {
          submitting = false;
        });
      }
    }
  }

  Future<void> completeOAuthSignIn({
    OAuthCallbackPayload? callback,
  }) async {
    final runtime = AppRuntimeScope.of(context);
    final provider = callback?.provider ?? oauthProvider;
    final startId = callback?.oauthStartId ?? oauthStartId;
    setState(() {
      submitting = true;
      errorText = null;
    });
    try {
      if (provider == null || startId == null) {
        throw StateError('Start social login first.');
      }
      _ensureAuthProviderEnabled(runtime, provider);
      final code = callback?.code ?? oauthCodeController.text.trim();
      if (code.isEmpty) {
        throw ArgumentError('OAuth callback code is required.');
      }
      final result = await runtime.client.completeOAuth(
        provider: provider,
        oauthStartId: startId,
        code: code,
        state: callback?.state ?? oauthStateController.text.trim(),
        endUserRef: runtime.endUserRef,
      );
      runtime.applyAuthenticatedAccount(result.account);
      if (!mounted) {
        return;
      }
      setState(() {
        resultText =
            '${result.provider} verified for ${result.account.accountRefMasked}.';
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        errorText = authErrorMessage(runtime.strings, error);
      });
    } finally {
      if (mounted) {
        setState(() {
          submitting = false;
        });
      }
    }
  }

  void _ensureAuthProviderEnabled(AppRuntime runtime, String provider) {
    final enabledProviders = runtime
        .effectiveCapabilities.normalizedAuthProviders
        .map((item) => item.wireValue)
        .toSet();
    if (!enabledProviders.contains(provider)) {
      throw StateError('Auth provider $provider is not enabled for this app.');
    }
  }

  Future<void> handleOAuthCallbackUri(Uri uri) async {
    final payload = parseOAuthCallbackUri(uri);
    if (payload == null || !mounted) {
      return;
    }
    await completeOAuthSignIn(callback: payload);
  }

  OAuthCallbackPayload? parseOAuthCallbackUri(Uri uri) {
    final query = uri.queryParameters;
    final code = query['code']?.trim();
    if (code == null || code.isEmpty) {
      return null;
    }
    final hostMatches = uri.host == 'auth';
    final pathSegments = uri.pathSegments;
    final pathLooksLikeOAuth = pathSegments.contains('oauth') ||
        pathSegments.contains('callback') ||
        pathSegments.contains('auth');
    if (!hostMatches && !pathLooksLikeOAuth && query['oauthStartId'] == null) {
      return null;
    }
    final pathProvider = _providerFromPath(pathSegments);
    return OAuthCallbackPayload(
      code: code,
      provider: query['provider']?.trim().isNotEmpty == true
          ? query['provider']!.trim()
          : pathProvider,
      oauthStartId: query['oauthStartId']?.trim().isNotEmpty == true
          ? query['oauthStartId']!.trim()
          : null,
      state: query['state']?.trim().isNotEmpty == true
          ? query['state']!.trim()
          : null,
    );
  }

  String? _providerFromPath(List<String> pathSegments) {
    final oauthIndex = pathSegments.indexOf('oauth');
    if (oauthIndex >= 0 && oauthIndex + 1 < pathSegments.length) {
      return pathSegments[oauthIndex + 1];
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final capabilities = runtime.effectiveCapabilities;
    final tokens = templateTokensFor(
      capabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    if (tokens.name == 'CoolShow Short') {
      return _CoolShowAuthScaffold(
        appName: runtime.appName,
        tokens: tokens,
        capabilities: capabilities,
        emailController: emailController,
        emailCodeController: emailCodeController,
        oauthCodeController: oauthCodeController,
        oauthStateController: oauthStateController,
        emailChallengeId: emailChallengeId,
        oauthStartId: oauthStartId,
        oauthProvider: oauthProvider,
        submitting: submitting,
        resultText: resultText,
        errorText: errorText,
        onStartProvider: startProvider,
        onVerifyEmail: verifyEmailChallenge,
        onCompleteOAuth: completeOAuthSignIn,
      );
    }
    return Scaffold(
      appBar: AppBar(title: const Text('Login / Register')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Icon(Icons.play_circle_fill_rounded, size: 64, color: tokens.primary),
          const SizedBox(height: 14),
          Text(
            'Continue watching on ${runtime.appName}',
            style: Theme.of(
              context,
            ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 8),
          const Text(
            'Auth providers are configured by the tenant backend. Provider secrets stay on Tenant Edge.',
          ),
          const SizedBox(height: 18),
          if (capabilities.normalizedAuthProviders.contains(
            AuthProvider.email,
          )) ...[
            TextField(
              controller: emailController,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(
                labelText: 'Email',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 10),
            if (emailChallengeId != null) ...[
              TextField(
                key: const ValueKey('email-verification-code-input'),
                controller: emailCodeController,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Email verification code',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 10),
              FilledButton.icon(
                onPressed: submitting ? null : verifyEmailChallenge,
                icon: const Icon(Icons.verified_outlined),
                label: const Text('Verify email'),
              ),
              const SizedBox(height: 10),
            ],
          ],
          if (oauthStartId != null) ...[
            TextField(
              key: const ValueKey('oauth-callback-code-input'),
              controller: oauthCodeController,
              decoration: const InputDecoration(
                labelText: 'OAuth callback code',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 10),
            TextField(
              key: const ValueKey('oauth-callback-state-input'),
              controller: oauthStateController,
              decoration: const InputDecoration(
                labelText: 'OAuth callback state',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 10),
            FilledButton.icon(
              onPressed: submitting ? null : completeOAuthSignIn,
              icon: const Icon(Icons.verified_user_outlined),
              label: Text('Complete ${oauthProvider ?? 'social'} sign-in'),
            ),
            const SizedBox(height: 10),
          ],
          if (resultText != null) ...[
            Text(
              resultText!,
              style: TextStyle(
                color: tokens.primary,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
          ],
          if (errorText != null) ...[
            Text(
              errorText!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
            const SizedBox(height: 10),
          ],
          for (final provider in capabilities.normalizedAuthProviders)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: OutlinedButton.icon(
                onPressed: submitting ? null : () => startProvider(provider),
                icon: Icon(
                  provider.wireValue == 'apple'
                      ? Icons.apple
                      : Icons.login_outlined,
                ),
                label: Text('Continue with ${provider.wireValue}'),
              ),
            ),
          const SizedBox(height: 10),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Continue as guest'),
          ),
        ],
      ),
    );
  }
}

class _CoolShowAuthScaffold extends StatelessWidget {
  const _CoolShowAuthScaffold({
    required this.appName,
    required this.tokens,
    required this.capabilities,
    required this.emailController,
    required this.emailCodeController,
    required this.oauthCodeController,
    required this.oauthStateController,
    required this.submitting,
    required this.onStartProvider,
    required this.onVerifyEmail,
    required this.onCompleteOAuth,
    this.emailChallengeId,
    this.oauthStartId,
    this.oauthProvider,
    this.resultText,
    this.errorText,
  });

  final String appName;
  final TemplateTokens tokens;
  final AppCapabilities capabilities;
  final TextEditingController emailController;
  final TextEditingController emailCodeController;
  final TextEditingController oauthCodeController;
  final TextEditingController oauthStateController;
  final bool submitting;
  final String? emailChallengeId;
  final String? oauthStartId;
  final String? oauthProvider;
  final String? resultText;
  final String? errorText;
  final Future<void> Function(AuthProvider provider) onStartProvider;
  final Future<void> Function() onVerifyEmail;
  final Future<void> Function({OAuthCallbackPayload? callback}) onCompleteOAuth;

  @override
  Widget build(BuildContext context) {
    final providers = capabilities.normalizedAuthProviders;
    return Scaffold(
      backgroundColor: tokens.background,
      body: SafeArea(
        child: ListView(
          padding: EdgeInsets.zero,
          children: [
            SizedBox(
              height: 272,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Image.asset(
                    'assets/visuals/scene_01.jpg',
                    fit: BoxFit.cover,
                  ),
                  const DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Color(0x9906070A),
                          Color(0x2206070A),
                          Color(0xFF06070A),
                        ],
                      ),
                    ),
                  ),
                  Positioned(
                    left: 18,
                    right: 18,
                    top: 18,
                    child: Row(
                      children: [
                        const _CoolShowMark(size: 28),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            appName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                        ),
                        IconButton(
                          onPressed: () {},
                          icon: const Icon(
                            Icons.language_rounded,
                            color: Colors.white,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Positioned(
                    left: 18,
                    right: 18,
                    bottom: 22,
                    child: Text(
                      'Continue the next episode',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 27,
                        height: 1.02,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Container(
              margin: const EdgeInsets.fromLTRB(16, 0, 16, 24),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFF141820),
                borderRadius: BorderRadius.circular(22),
                border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
                boxShadow: const [
                  BoxShadow(
                    color: Color(0x66000000),
                    blurRadius: 32,
                    offset: Offset(0, 16),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Sign in to sync history, unlocks, and language.',
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.72),
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 14),
                  if (providers.contains(AuthProvider.email)) ...[
                    _CoolShowTextField(
                      controller: emailController,
                      label: 'Email',
                      icon: Icons.mail_outline_rounded,
                      keyboardType: TextInputType.emailAddress,
                    ),
                    const SizedBox(height: 10),
                    const _CoolShowReadonlyField(
                      label: 'Password',
                      value: 'Email code or tenant OAuth',
                      icon: Icons.lock_outline_rounded,
                    ),
                    const SizedBox(height: 12),
                    _CoolShowPrimaryButton(
                      label: 'Sign in with Email',
                      icon: Icons.mail_outline_rounded,
                      tokens: tokens,
                      onPressed: submitting
                          ? null
                          : () => onStartProvider(AuthProvider.email),
                    ),
                  ],
                  if (emailChallengeId != null) ...[
                    const SizedBox(height: 10),
                    _CoolShowTextField(
                      controller: emailCodeController,
                      label: 'Email verification code',
                      icon: Icons.verified_outlined,
                      keyboardType: TextInputType.number,
                    ),
                    const SizedBox(height: 10),
                    _CoolShowPrimaryButton(
                      label: 'Verify email',
                      icon: Icons.verified_rounded,
                      tokens: tokens,
                      onPressed: submitting ? null : onVerifyEmail,
                    ),
                  ],
                  for (final provider in providers)
                    if (provider != AuthProvider.email)
                      Padding(
                        padding: const EdgeInsets.only(top: 10),
                        child: _CoolShowProviderButton(
                          provider: provider,
                          submitting: submitting,
                          onPressed: () => onStartProvider(provider),
                        ),
                      ),
                  if (oauthStartId != null) ...[
                    const SizedBox(height: 10),
                    _CoolShowTextField(
                      controller: oauthCodeController,
                      label: 'OAuth callback code',
                      icon: Icons.key_rounded,
                    ),
                    const SizedBox(height: 10),
                    _CoolShowTextField(
                      controller: oauthStateController,
                      label: 'OAuth callback state',
                      icon: Icons.shield_outlined,
                    ),
                    const SizedBox(height: 10),
                    _CoolShowPrimaryButton(
                      label: 'Complete ${oauthProvider ?? 'social'} sign-in',
                      icon: Icons.verified_user_outlined,
                      tokens: tokens,
                      onPressed: submitting ? null : () => onCompleteOAuth(),
                    ),
                  ],
                  if (resultText != null) ...[
                    const SizedBox(height: 12),
                    Text(
                      resultText!,
                      style: TextStyle(
                        color: tokens.primary,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ],
                  if (errorText != null) ...[
                    const SizedBox(height: 12),
                    Text(
                      errorText!,
                      style: const TextStyle(
                        color: Color(0xFFFF6161),
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  TextButton(
                    onPressed: () => Navigator.of(context).maybePop(),
                    child: const Text('Continue as guest'),
                  ),
                  Text(
                    'By continuing, you agree to Terms and Privacy Policy.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.42),
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CoolShowMark extends StatelessWidget {
  const _CoolShowMark({required this.size});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      'assets/visuals/coolshow-mark.png',
      width: size,
      height: size,
      fit: BoxFit.contain,
      errorBuilder: (_, __, ___) => Icon(
        Icons.play_arrow_rounded,
        color: Colors.white,
        size: size,
      ),
    );
  }
}

class _CoolShowTextField extends StatelessWidget {
  const _CoolShowTextField({
    required this.controller,
    required this.label,
    required this.icon,
    this.keyboardType,
  });

  final TextEditingController controller;
  final String label;
  final IconData icon;
  final TextInputType? keyboardType;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      keyboardType: keyboardType,
      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800),
      decoration: InputDecoration(
        prefixIcon: Icon(icon, color: Colors.white70),
        labelText: label,
        labelStyle: const TextStyle(color: Colors.white54),
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.07),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.08)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFFFFB23F)),
        ),
      ),
    );
  }
}

class _CoolShowReadonlyField extends StatelessWidget {
  const _CoolShowReadonlyField({
    required this.label,
    required this.value,
    required this.icon,
  });

  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Row(
        children: [
          Icon(icon, color: Colors.white70),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: const TextStyle(color: Colors.white54, fontSize: 12),
                ),
                Text(
                  value,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _CoolShowPrimaryButton extends StatelessWidget {
  const _CoolShowPrimaryButton({
    required this.label,
    required this.icon,
    required this.tokens,
    required this.onPressed,
  });

  final String label;
  final IconData icon;
  final TemplateTokens tokens;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return FilledButton.icon(
      style: FilledButton.styleFrom(
        backgroundColor: tokens.primary,
        foregroundColor: const Color(0xFF171008),
        minimumSize: const Size.fromHeight(48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
      onPressed: onPressed,
      icon: Icon(icon),
      label: Text(label, maxLines: 1, overflow: TextOverflow.ellipsis),
    );
  }
}

class _CoolShowProviderButton extends StatelessWidget {
  const _CoolShowProviderButton({
    required this.provider,
    required this.submitting,
    required this.onPressed,
  });

  final AuthProvider provider;
  final bool submitting;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final providerName = provider.wireValue;
    final isApple = provider == AuthProvider.apple;
    return OutlinedButton.icon(
      style: OutlinedButton.styleFrom(
        foregroundColor: Colors.white,
        minimumSize: const Size.fromHeight(46),
        side: BorderSide(color: Colors.white.withValues(alpha: 0.12)),
        backgroundColor:
            isApple ? Colors.white.withValues(alpha: 0.13) : Colors.white10,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
      onPressed: submitting ? null : onPressed,
      icon: Icon(isApple ? Icons.apple : Icons.login_outlined),
      label: Text(
        'Continue with $providerName',
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
    );
  }
}

String authErrorMessage(AppStrings strings, Object? error) {
  if (error is AppApiException) {
    return strings.authFailed;
  }
  return '$error';
}
